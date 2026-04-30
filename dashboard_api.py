"""
Beast V3 — Dashboard API Server
Serves JSON from SQLite for the React frontend.
Runs on VM port 8080.
"""
import sys, os, io
if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv('.env')

from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import hmac
import secrets
import time as _time
from functools import wraps

# ── Authentication ─────────────────────────────────────
AUTH_USERNAME = os.getenv('DASHBOARD_USER', 'akash')
AUTH_PASSWORD_HASH = os.getenv('DASHBOARD_PASSWORD_HASH', 
    hashlib.sha256('B3astTerminal!'.encode()).hexdigest())
JWT_SECRET = os.getenv('JWT_SECRET', secrets.token_hex(32))
JWT_EXPIRY = 86400  # 24 hours

_active_tokens = {}
_failed_attempts = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300


def _create_token(username: str) -> str:
    payload = f"{username}:{int(_time.time()) + JWT_EXPIRY}:{secrets.token_hex(8)}"
    signature = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = f"{payload}:{signature}"
    import base64
    encoded = base64.b64encode(token.encode()).decode()
    _active_tokens[encoded] = {'username': username, 'expires': int(_time.time()) + JWT_EXPIRY}
    return encoded


def _verify_token(token: str) -> bool:
    """Verify token by checking signature — works even after API restart."""
    if not token or token == 'null' or token == 'undefined' or len(token) < 10:
        return False
    # Check in-memory cache first
    session = _active_tokens.get(token)
    if session:
        if int(_time.time()) > session['expires']:
            _active_tokens.pop(token, None)
            return False
        return True
    # Verify signature (works after restart — no memory needed)
    try:
        import base64
        decoded = base64.b64decode(token).decode()
        parts = decoded.rsplit(':', 1)
        if len(parts) != 2:
            return False
        payload, signature = parts
        expected_sig = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return False
        # Check expiry from payload
        payload_parts = payload.split(':')
        if len(payload_parts) >= 2:
            expiry = int(payload_parts[1])
            if int(_time.time()) > expiry:
                return False
        # Valid — re-cache it
        username = payload_parts[0] if payload_parts else 'unknown'
        _active_tokens[token] = {'username': username, 'expires': expiry}
        return True
    except Exception:
        return False


def _check_rate_limit(ip: str) -> bool:
    if ip not in _failed_attempts:
        return True
    count, last_time = _failed_attempts[ip]
    if count >= MAX_FAILED_ATTEMPTS:
        if int(_time.time()) - last_time < LOCKOUT_SECONDS:
            return False
        else:
            _failed_attempts.pop(ip)
            return True
    return True


def _record_failure(ip: str):
    if ip in _failed_attempts:
        count, _ = _failed_attempts[ip]
        _failed_attempts[ip] = (count + 1, int(_time.time()))
    else:
        _failed_attempts[ip] = (1, int(_time.time()))


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check API key first (bot/system calls)
        api_key = request.headers.get('X-API-Key', '')
        if api_key == os.getenv('AI_API_KEY', 'beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c'):
            return f(*args, **kwargs)
        # Check Bearer token (dashboard login)
        auth_header = request.headers.get('Authorization', '')
        token = ''
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        if not token:
            token = request.cookies.get('beast_token', '')
        if not token:
            token = request.args.get('token', '')
        if token and _verify_token(token):
            return f(*args, **kwargs)
        # No valid auth — return 401
        return jsonify({'error': 'Unauthorized', 'login_required': True}), 401
    return decorated

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "X-API-Key"],
     methods=["GET", "POST", "OPTIONS"])


@app.route('/api/login', methods=['POST'])
def login():
    ip = request.remote_addr or 'unknown'
    if not _check_rate_limit(ip):
        remaining = LOCKOUT_SECONDS - (int(_time.time()) - _failed_attempts.get(ip, (0, 0))[1])
        return jsonify({'error': f'Too many failed attempts. Locked for {remaining}s', 'locked': True}), 429
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if username == AUTH_USERNAME and password_hash == AUTH_PASSWORD_HASH:
        token = _create_token(username)
        response = jsonify({'success': True, 'token': token, 'username': username, 'expires_in': JWT_EXPIRY})
        response.set_cookie('beast_token', token, max_age=JWT_EXPIRY, httponly=True, samesite='Strict', secure=True)
        try:
            from db_postgres import BeastDB
            BeastDB().log_activity('LOGIN', reason=f'Dashboard login from {ip}', source='dashboard')
        except:
            pass
        return response
    else:
        _record_failure(ip)
        attempts = _failed_attempts.get(ip, (0, 0))[0]
        remaining = MAX_FAILED_ATTEMPTS - attempts
        return jsonify({'error': 'Invalid credentials', 'attempts_remaining': remaining}), 401


@app.route('/api/logout', methods=['POST'])
def logout():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        token = request.cookies.get('beast_token', '')
    _active_tokens.pop(token, None)
    response = jsonify({'success': True, 'message': 'Logged out'})
    response.delete_cookie('beast_token')
    return response


@app.route('/api/auth-status')
def auth_status():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        token = request.cookies.get('beast_token', '')
    valid = _verify_token(token)
    return jsonify({'authenticated': valid})


ET = ZoneInfo("America/New_York")

def _get_db():
    from trade_db import TradeDB
    return TradeDB()

def _get_gateway():
    from order_gateway import OrderGateway
    return OrderGateway(
        os.getenv('ALPACA_API_KEY', ''),
        os.getenv('ALPACA_SECRET_KEY', ''),
        paper=True
    )

# ── PORTFOLIO ──────────────────────────────────────────

@app.route('/api/portfolio')
@require_auth
def portfolio():
    """Live portfolio: positions, P&L, equity."""
    gw = _get_gateway()
    positions = gw.get_positions()
    acct = gw.get_account()
    orders = gw.get_open_orders()

    # Load cached TV/sentiment/AI data from trade_db
    db = _get_db()
    cached_tv = {}
    cached_sent = {}
    cached_ai = {}
    if db:
        try:
            import sqlite3
            conn = sqlite3.connect(db.db_path)
            conn.row_factory = sqlite3.Row
            for row in conn.execute("SELECT symbol, data, timestamp FROM tv_cache ORDER BY timestamp DESC"):
                if row['symbol'] not in cached_tv:
                    cached_tv[row['symbol']] = {'data': row['data'], 'time': row['timestamp']}
            for row in conn.execute("SELECT symbol, total_score, yahoo_score, reddit_score, analyst_score, timestamp FROM sentiment_cache ORDER BY timestamp DESC"):
                if row['symbol'] not in cached_sent:
                    cached_sent[row['symbol']] = dict(row)
            for row in conn.execute("SELECT symbol, action, confidence, reasoning, ai_source, timestamp FROM ai_cache ORDER BY timestamp DESC"):
                if row['symbol'] not in cached_ai:
                    cached_ai[row['symbol']] = dict(row)
            conn.close()
        except Exception:
            pass

    pos_data = []
    daily_pl = 0
    for p in positions:
        cost = p.avg_entry * p.qty
        pct = (p.unrealized_pl / cost * 100) if cost > 0 else 0
        # Intraday P&L (today's change only)
        intra_pl = float(p.unrealized_intraday_pl) if hasattr(p, 'unrealized_intraday_pl') and p.unrealized_intraday_pl else 0
        intra_pct = float(p.unrealized_intraday_plpc) if hasattr(p, 'unrealized_intraday_plpc') and p.unrealized_intraday_plpc else 0
        daily_pl += intra_pl
        entry = {
            'symbol': p.symbol,
            'qty': p.qty,
            'avg_entry': float(p.avg_entry),
            'current_price': float(p.current_price),
            'market_value': float(p.market_value),
            'unrealized_pl': float(p.unrealized_pl),
            'pnl': float(p.unrealized_pl),
            'pct': round(pct, 2),
            'pnl_pct': round(pct, 2),
            'intraday_pl': intra_pl,
            'intraday_pct': round(intra_pct * 100, 2) if abs(intra_pct) < 1 else round(intra_pct, 2),
            'is_green': p.unrealized_pl >= 0,
            'change_today': round(float(p.change_today) * 100, 2) if hasattr(p, 'change_today') and p.change_today else 0,
            'last_tv_data': cached_tv.get(p.symbol),
            'last_sentiment': cached_sent.get(p.symbol),
            'last_ai_verdict': cached_ai.get(p.symbol),
        }
        pos_data.append(entry)

    total_pl = sum(float(p.unrealized_pl) for p in positions)

    # Serialize orders to plain dicts (React can't render raw objects)
    orders_data = []
    for o in orders:
        if isinstance(o, dict):
            orders_data.append(o)
        else:
            orders_data.append({
                'id': str(getattr(o, 'id', '')),
                'symbol': getattr(o, 'symbol', ''),
                'side': str(getattr(o, 'side', '')),
                'qty': str(getattr(o, 'qty', '')),
                'type': str(getattr(o, 'type', '')),
                'status': str(getattr(o, 'status', '')),
                'limit_price': str(getattr(o, 'limit_price', '') or ''),
                'trail_percent': str(getattr(o, 'trail_percent', '') or ''),
            })

    return jsonify({
        'equity': float(acct.get('equity', 0)),
        'buying_power': float(acct.get('buying_power', 0)),
        'cash': float(acct.get('cash', 0)),
        'total_pl': round(total_pl, 2),
        'pnl': round(total_pl, 2),
        'daily_pl': round(daily_pl, 2),
        'positions': sorted(pos_data, key=lambda x: x['unrealized_pl'], reverse=True),
        'open_orders': orders_data,
        'positions_count': len(positions),
        'orders_count': len(orders_data),
        'green_count': sum(1 for p in pos_data if p['unrealized_pl'] >= 0),
        'red_count': sum(1 for p in pos_data if p['unrealized_pl'] < 0),
        'timestamp': datetime.now(ET).isoformat(),
    })


# ── TRADES ─────────────────────────────────────────────

@app.route('/api/trades')
@require_auth
def trades():
    """Trade history with reasoning. Falls back to Alpaca orders if DB is empty."""
    db = _get_db()
    limit = request.args.get('limit', 50, type=int)
    all_trades = []
    if db:
        try:
            all_trades = db.get_all_trades(limit)
            db.close()
        except Exception:
            pass
    # Fallback: read from Alpaca closed orders
    if not all_trades:
        try:
            gw = _get_gateway()
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=limit)
            orders = gw.client.get_orders(req)
            for o in orders:
                if o.filled_at:
                    all_trades.append({
                        'symbol': o.symbol,
                        'side': o.side.value,
                        'qty': str(o.filled_qty),
                        'price': str(o.filled_avg_price) if o.filled_avg_price else '?',
                        'time': o.filled_at.isoformat() if o.filled_at else '',
                        'status': o.status.value,
                        'client_order_id': str(o.client_order_id or ''),
                        'order_type': str(o.type.value) if o.type else 'unknown',
                    })
        except Exception:
            pass
    return jsonify({'trades': all_trades, 'count': len(all_trades)})

@app.route('/api/trades/today')
@require_auth
def trades_today():
    db = _get_db()
    today_trades = []
    if db:
        try:
            today_trades = db.get_trades_today()
            db.close()
        except Exception:
            pass
    # Fallback: Alpaca closed orders filled today
    if not today_trades:
        try:
            from datetime import date
            gw = _get_gateway()
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=100,
                                   after=datetime.combine(date.today(), datetime.min.time()).isoformat() + 'Z')
            orders = gw.client.get_orders(req)
            for o in orders:
                if o.filled_at:
                    today_trades.append({
                        'symbol': o.symbol,
                        'side': o.side.value,
                        'qty': str(o.filled_qty),
                        'price': str(o.filled_avg_price) if o.filled_avg_price else '?',
                        'time': o.filled_at.isoformat() if o.filled_at else '',
                        'status': o.status.value,
                        'client_order_id': str(o.client_order_id or ''),
                    })
        except Exception:
            pass
    return jsonify({'trades': today_trades, 'count': len(today_trades)})


# ── SCANS ──────────────────────────────────────────────

@app.route('/api/scans')
@require_auth
def scans():
    """Scan history — every 5-min scan result."""
    db = _get_db()
    limit = request.args.get('limit', 50, type=int)
    scan_history = db.get_scan_history(limit)
    db.close()
    return jsonify({'scans': scan_history, 'count': len(scan_history)})


# ── EQUITY CURVE ───────────────────────────────────────

@app.route('/api/equity')
@require_auth
def equity():
    """Equity curve data for charting."""
    db = _get_db()
    limit = request.args.get('limit', 200, type=int)
    curve = db.get_equity_curve(limit)
    curve.reverse()  # oldest first for charts
    db.close()
    return jsonify({'data': curve, 'count': len(curve)})


# ── ANALYTICS ──────────────────────────────────────────

@app.route('/api/analytics')
@require_auth
def analytics():
    """Full analytics: tries DB first, falls back to Alpaca portfolio history."""
    db = _get_db()
    db_result = None
    if db:
        try:
            db_result = {
                'overall': db.get_overall_stats(),
                'by_strategy': db.get_stats_by_strategy(),
                'by_stock': db.get_stats_by_stock(),
                'by_regime': db.get_stats_by_regime(),
                'by_day': db.get_stats_by_day(30),
                'streak': db.get_streak(),
            }
            db.close()
            # Check if DB data is actually populated
            overall = db_result.get('overall', {})
            if overall and overall.get('total_trades', 0) > 0:
                return jsonify(db_result)
        except Exception:
            pass

    # Fallback: compute from Alpaca portfolio history + orders
    try:
        gw = _get_gateway()
        from alpaca.trading.requests import GetPortfolioHistoryRequest
        hist = gw.client.get_portfolio_history(period='1M', timeframe='1D')

        equity_data = []
        pnl_data = []
        if hist and hist.timestamp:
            for i, ts in enumerate(hist.timestamp):
                equity_data.append({'time': ts, 'equity': hist.equity[i]})
                if hist.profit_loss:
                    pnl_data.append(hist.profit_loss[i])

        total_pnl = sum(pnl_data) if pnl_data else 0
        wins = sum(1 for p in pnl_data if p > 0)
        losses = sum(1 for p in pnl_data if p < 0)
        win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0

        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=200)
        closed = gw.client.get_orders(req)
        filled = [o for o in closed if o.filled_at]

        return jsonify({
            'total_trades': len(filled),
            'win_rate': round(win_rate, 1),
            'total_pnl': round(total_pnl, 2),
            'wins': wins,
            'losses': losses,
            'equity_curve': equity_data[-30:],
            'best_day': round(max(pnl_data), 2) if pnl_data else 0,
            'worst_day': round(min(pnl_data), 2) if pnl_data else 0,
            # Preserve expected structure
            'overall': {'total_trades': len(filled), 'win_rate': round(win_rate, 1), 'total_pnl': round(total_pnl, 2)},
            'by_strategy': db_result.get('by_strategy', {}) if db_result else {},
            'by_stock': db_result.get('by_stock', {}) if db_result else {},
            'by_regime': db_result.get('by_regime', {}) if db_result else {},
            'by_day': db_result.get('by_day', []) if db_result else [],
            'streak': db_result.get('streak', {}) if db_result else {},
        })
    except Exception as e:
        return jsonify({
            'total_trades': 0, 'win_rate': 0, 'total_pnl': 0,
            'wins': 0, 'losses': 0, 'best_day': 0, 'worst_day': 0,
            'equity_curve': [],
            'overall': {}, 'by_strategy': {}, 'by_stock': {}, 'by_regime': {}, 'by_day': [], 'streak': {},
            'error': str(e),
            'market_closed': True,
            'message': 'Market closed — analytics update at next open',
        })


# ── SYSTEM STATUS ──────────────────────────────────────

@app.route('/api/system')
@require_auth
def system_status():
    """System health: AI, TV, tunnel, uptime."""
    import requests as req

    # AI health
    ai_ok = False
    ai_url = os.getenv('AI_API_URL', '')
    try:
        r = req.get(f"{ai_url}/health", timeout=5)
        ai_ok = r.status_code == 200 and r.json().get('ai_available', False)
    except:
        pass

    # TV health
    tv_ok = False
    try:
        from tv_cdp_client import TVClient
        tv_ok = TVClient().health_check()
    except:
        pass

    # Discord bot (check if python process running discord_bot.py)
    import subprocess
    bot_running = False
    try:
        r = subprocess.run('tasklist /fi "imagename eq python.exe" /fo csv /nh',
                          shell=True, capture_output=True, text=True, timeout=5)
        bot_running = 'python' in r.stdout.lower()
    except:
        pass

    return jsonify({
        'ai': {'status': 'online' if ai_ok else 'offline', 'url': ai_url},
        'tv': {'status': 'connected' if tv_ok else 'disconnected'},
        'bot': {'status': 'running' if bot_running else 'stopped'},
        'timestamp': datetime.now(ET).isoformat(),
        'uptime': 'N/A',
    })


# ── DEBUG LOG ──────────────────────────────────────────

@app.route('/api/debug')
@require_auth
def debug_log():
    db = _get_db()
    component = request.args.get('component', None)
    limit = request.args.get('limit', 100, type=int)
    entries = db.get_debug_log(limit, component)
    db.close()
    return jsonify({'entries': entries, 'count': len(entries)})


# ── ALERTS ─────────────────────────────────────────────

@app.route('/api/alerts')
@require_auth
def alerts():
    db = _get_db()
    rows = db.conn.execute(
        "SELECT * FROM alerts_log ORDER BY timestamp DESC LIMIT 50"
    ).fetchall()
    db.close()
    return jsonify({'alerts': [dict(r) for r in rows]})


# ── HEALTH ─────────────────────────────────────────────

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now(ET).isoformat()})


# ── INTRADAY P&L (for live chart) ──────────────────────

@app.route('/api/intraday')
@require_auth
def intraday_pnl():
    """Intraday equity snapshots for live P&L chart."""
    db = _get_db()
    rows = db.conn.execute("""
        SELECT timestamp, equity, total_pl, positions_count
        FROM equity_curve
        WHERE date(timestamp) = date('now')
        ORDER BY timestamp ASC
    """).fetchall()
    db.close()
    return jsonify({'data': [dict(r) for r in rows], 'count': len(rows)})


# ── ACTION FEED (live timeline) ────────────────────────

@app.route('/api/actions')
@require_auth
def action_feed():
    """Live feed of all bot actions: trades, alerts, scans + Alpaca fills."""
    limit = request.args.get('limit', 50, type=int)
    all_actions = []

    # DB-based actions (trades, alerts, scans)
    db = _get_db()
    if db:
        try:
            trades = db.conn.execute("""
                SELECT created_at as timestamp, 'TRADE' as type,
                       side || ' ' || symbol || ' x' || qty || ' @ $' || printf('%.2f', price) as title,
                       reason as detail
                FROM trades ORDER BY created_at DESC LIMIT ?
            """, (limit,)).fetchall()

            alerts = db.conn.execute("""
                SELECT timestamp, alert_type as type, symbol as title, message as detail
                FROM alerts_log ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()

            scans = db.conn.execute("""
                SELECT timestamp, 'SCAN' as type,
                       scan_type || ' | ' || regime || ' | SPY:' || printf('%.2f%%', spy_change*100) as title,
                       'TV:' || tv_reads || ' Sent:' || sentiments || ' AI:' || ai_calls || ' Trump:' || trump_score as detail
                FROM scan_log ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()

            all_actions = [dict(r) for r in trades] + [dict(r) for r in alerts] + [dict(r) for r in scans]
            db.close()
        except Exception:
            pass

    # Alpaca fills as fallback/supplement
    try:
        gw = _get_gateway()
        activities = gw.client.get_account_activities(activity_types=['FILL'])
        for a in (activities or [])[:limit]:
            action_type = 'BUY' if getattr(a, 'side', '') == 'buy' else 'SELL'
            cid = str(getattr(a, 'order_id', '') or '')
            if 'scalp' in cid: icon = 'SCALP'
            elif 'runner' in cid: icon = 'RUNNER'
            elif 'trail' in cid: icon = 'STOP'
            elif 'dip' in cid or 'quickbuy' in cid: icon = 'DIP-BUY'
            elif 'protect' in cid: icon = 'PROTECT'
            else: icon = action_type

            tx_time = ''
            if hasattr(a, 'transaction_time') and a.transaction_time:
                tx_time = a.transaction_time.isoformat()

            all_actions.append({
                'timestamp': tx_time,
                'type': icon,
                'title': f"{icon} {getattr(a, 'symbol', '?')} x{getattr(a, 'qty', '?')} @ ${getattr(a, 'price', '?')}",
                'detail': cid,
                'symbol': getattr(a, 'symbol', ''),
                'side': getattr(a, 'side', ''),
                'qty': str(getattr(a, 'qty', '')),
                'price': str(getattr(a, 'price', '')),
                'time': tx_time,
                'reason': cid,
            })
    except Exception:
        pass

    all_actions.sort(key=lambda x: x.get('timestamp', '') or x.get('time', ''), reverse=True)
    return jsonify({'actions': all_actions[:limit]})


# ── SENTIMENT MATRIX ───────────────────────────────────

@app.route('/api/sentiment')
@require_auth
def sentiment_matrix():
    """Per-stock sentiment scores from all sources."""
    try:
        from sentiment_analyst import SentimentAnalyst
        gw = _get_gateway()
        positions = gw.get_positions()
        sa = SentimentAnalyst()
        results = {}
        for p in positions[:12]:
            try:
                s = sa.analyze(p.symbol)
                results[p.symbol] = {
                    'yahoo': s.yahoo_score, 'reddit': s.reddit_score,
                    'analyst': s.analyst_score, 'total': s.total_score,
                }
            except:
                results[p.symbol] = {'yahoo': 0, 'reddit': 0, 'analyst': 0, 'total': 0}
        # Trump
        try:
            t_score, t_headlines = sa.get_trump_sentiment()
            results['_trump'] = {'score': t_score, 'headlines': t_headlines[:5]}
        except:
            results['_trump'] = {'score': 0, 'headlines': []}
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/')
def index():
    return jsonify({
        'name': 'Beast V3 Dashboard API',
        'endpoints': [
            '/api/portfolio', '/api/trades', '/api/trades/today',
            '/api/scans', '/api/equity', '/api/analytics',
            '/api/system', '/api/debug', '/api/alerts', '/api/health',
            '/api/intraday', '/api/actions', '/api/sentiment',
            '/api/runners', '/api/sectors', '/api/trailing-stops', '/api/news',
            '/api/sharpe', '/api/correlation', '/api/daily-pnl',
            '/api/ai-verdicts', '/api/decision-log',
        ]
    })


# ── RUNNERS (pre-market, market, post-market) ─────────

@app.route('/api/runners')
@require_auth
def runners():
    """Top runners across all sessions. Uses 3-layer detection."""
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import MostActivesRequest, StockSnapshotRequest
        
        client = StockHistoricalDataClient(
            os.getenv('ALPACA_API_KEY', ''), os.getenv('ALPACA_SECRET_KEY', '')
        )
        
        # Get most active
        req = MostActivesRequest(top=20, by='volume')
        actives = client.get_most_actives(req)
        
        active_syms = []
        if hasattr(actives, 'most_actives'):
            for a in actives.most_actives:
                sym = a.symbol if hasattr(a, 'symbol') else ''
                if sym and len(sym) <= 5:
                    active_syms.append(sym)
        
        # Get snapshots
        runners = []
        if active_syms:
            snap_req = StockSnapshotRequest(symbol_or_symbols=active_syms[:20], feed='iex')
            snaps = client.get_stock_snapshot(snap_req)
            for sym, s in snaps.items():
                try:
                    price = float(s.latest_trade.price) if s.latest_trade else 0
                    prev = float(s.previous_daily_bar.close) if s.previous_daily_bar else 0
                    if prev > 0 and price > 5:
                        pct = (price - prev) / prev * 100
                        runners.append({
                            'symbol': sym, 'price': round(price, 2),
                            'change_pct': round(pct, 2),
                            'prev_close': round(prev, 2),
                        })
                except:
                    pass
        
        runners.sort(key=lambda x: x['change_pct'], reverse=True)
        now = datetime.now(ET)
        session = 'pre-market' if now.hour < 9 else ('after-hours' if now.hour >= 16 else 'market')

        # Also include our held positions that are running today
        try:
            gw = _get_gateway()
            for p in gw.get_positions():
                pct = ((p.current_price - p.avg_entry) / p.avg_entry * 100) if p.avg_entry > 0 else 0
                if pct > 2:
                    runners.append({
                        'symbol': p.symbol, 'price': round(p.current_price, 2),
                        'change_pct': round(pct, 1), 'prev_close': round(p.avg_entry, 2),
                        'held': True,
                    })
            runners.sort(key=lambda x: x['change_pct'], reverse=True)
        except Exception:
            pass

        return jsonify({
            'session': session,
            'runners': runners[:15],
            'timestamp': now.isoformat(),
        })
    except Exception as e:
        return jsonify({
            'session': 'closed',
            'runners': [],
            'error': str(e),
            'message': 'Market closed — no active runners',
        })


# ── SECTOR HEATMAP ─────────────────────────────────────

@app.route('/api/sectors')
@require_auth
def sector_heatmap():
    """Sector rotation heatmap — all 14 sectors with avg % change."""
    try:
        from beast_mode_loop import ALL_SECTORS
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockSnapshotRequest
        
        client = StockHistoricalDataClient(
            os.getenv('ALPACA_API_KEY', ''), os.getenv('ALPACA_SECRET_KEY', '')
        )
        
        sectors = {}
        for sector_name, symbols in ALL_SECTORS.items():
            sample = symbols[:5]
            try:
                req = StockSnapshotRequest(symbol_or_symbols=sample, feed='iex')
                snaps = client.get_stock_snapshot(req)
                changes = []
                for sym, s in snaps.items():
                    try:
                        prev = float(s.previous_daily_bar.close)
                        curr = float(s.latest_trade.price)
                        if prev > 0:
                            changes.append((curr - prev) / prev * 100)
                    except:
                        pass
                avg = sum(changes) / len(changes) if changes else 0
                sectors[sector_name] = {
                    'avg_change': round(avg, 2),
                    'stocks_sampled': len(changes),
                    'stock_list': sample,
                }
            except:
                sectors[sector_name] = {'avg_change': 0, 'stocks_sampled': 0, 'stock_list': sample}
        
        return jsonify({
            'sectors': sectors,
            'timestamp': datetime.now(ET).isoformat(),
        })
    except Exception as e:
        return jsonify({
            'sectors': {},
            'error': str(e),
            'market_closed': True,
            'message': 'Sector data unavailable after hours',
        })


# ── TRAILING STOPS VISUALIZATION ───────────────────────

@app.route('/api/trailing-stops')
@require_auth
def trailing_stops():
    """Show all trailing stops with entry, current, HWM, stop levels."""
    try:
        gw = _get_gateway()
        positions = gw.get_positions()
        orders = gw.get_open_orders()
        
        trails = []
        for o in orders:
            if 'trailing' in str(o.get('type', '')).lower() or o.get('trail_percent'):
                sym = o.get('symbol', '')
                pos = next((p for p in positions if p.symbol == sym), None)
                trails.append({
                    'symbol': sym,
                    'qty': o.get('qty'),
                    'trail_percent': o.get('trail_percent'),
                    'stop_price': float(o.get('stop_price', 0)),
                    'hwm': float(o.get('hwm', 0)),
                    'entry': pos.avg_entry if pos else 0,
                    'current': pos.current_price if pos else 0,
                    'pnl': pos.unrealized_pl if pos else 0,
                    'gap_to_stop': round(
                        ((pos.current_price - float(o.get('stop_price', 0))) / pos.current_price * 100), 1
                    ) if pos and float(o.get('stop_price', 0)) > 0 else 0,
                })
        
        return jsonify({
            'trailing_stops': trails,
            'count': len(trails),
            'timestamp': datetime.now(ET).isoformat(),
        })
    except Exception as e:
        return jsonify({'error': str(e)})


# ── LIVE NEWS FEED ─────────────────────────────────────

@app.route('/api/news')
@require_auth
def news_feed():
    """Live macro news with sector tagging."""
    try:
        from sentiment_analyst import SentimentAnalyst
        sa = SentimentAnalyst()
        
        # Force fresh fetch by clearing stale cache entries
        for key in list(sa._cache.keys()):
            if key.startswith('gnews:'):
                del sa._cache[key]
        
        # Get Trump/tariff headlines
        t_score, t_headlines = sa.get_trump_sentiment()
        
        # Get market headlines
        _, m_headlines = sa._google_news_sentiment("breaking news stock market today")
        
        # Tag headlines with sectors using keyword mapping
        KEYWORD_SECTORS = {
            'oil': 'ENERGY', 'crude': 'ENERGY', 'iran': 'ENERGY',
            'chip': 'SEMI', 'semiconductor': 'SEMI', 'nvidia': 'SEMI',
            'ai ': 'CLOUD_IT', 'artificial intelligence': 'CLOUD_IT',
            'fed': 'FINANCIALS', 'rate': 'FINANCIALS', 'powell': 'FINANCIALS',
            'trump': 'POLITICS', 'tariff': 'TRADE', 'china': 'TRADE',
            'war': 'DEFENSE', 'military': 'DEFENSE',
            'fda': 'MEDICAL', 'drug': 'MEDICAL',
            'earnings': 'EARNINGS', 'revenue': 'EARNINGS',
        }
        
        tagged_news = []
        for h in (t_headlines + m_headlines)[:20]:
            tags = []
            h_lower = h.lower()
            for keyword, sector in KEYWORD_SECTORS.items():
                if keyword in h_lower:
                    tags.append(sector)
            tagged_news.append({
                'headline': h,
                'tags': list(set(tags)) or ['GENERAL'],
            })
        
        return jsonify({
            'trump_score': t_score,
            'news': tagged_news,
            'timestamp': datetime.now(ET).isoformat(),
        })
    except Exception as e:
        return jsonify({
            'trump_score': 0,
            'news': [],
            'error': str(e),
            'message': 'News feed temporarily unavailable',
        })


# ── SHARPE + DRAWDOWN ─────────────────────────────────

@app.route('/api/sharpe')
@require_auth
def sharpe_ratio():
    """Sharpe ratio and max drawdown."""
    db = _get_db()
    if not db:
        return jsonify({'error': 'no db'})
    sharpe = db.calculate_sharpe()
    drawdown = db.calculate_max_drawdown()
    db.close()
    return jsonify({**sharpe, **drawdown})


# ── CORRELATION CHECK ─────────────────────────────────

@app.route('/api/correlation')
@require_auth
def correlation():
    """Portfolio correlation check."""
    from correlation_check import CorrelationChecker
    gw = _get_gateway()
    positions = gw.get_positions()
    checker = CorrelationChecker()
    return jsonify(checker.check(positions))


# ── DAILY P&L ─────────────────────────────────────────

@app.route('/api/daily-pnl')
@require_auth
def daily_pnl_api():
    """Today's P&L."""
    db = _get_db()
    if not db:
        return jsonify({'error': 'no db'})
    result = db.get_daily_pnl()
    db.close()
    return jsonify(result)


# ── AI VERDICTS ───────────────────────────────────────

@app.route('/api/ai-verdicts')
@require_auth
def ai_verdicts():
    """AI analysis verdicts for all positions."""
    try:
        gw = _get_gateway()
        positions = gw.get_positions()

        from ai_brain import AIBrain
        brain = AIBrain()

        verdicts = []
        for p in positions:
            cached = brain.get_cached_analysis(p.symbol) if hasattr(brain, 'get_cached_analysis') else None
            verdicts.append({
                'symbol': p.symbol,
                'price': p.current_price,
                'pnl': round(p.unrealized_pl, 2),
                'pct': round(((p.current_price - p.avg_entry) / p.avg_entry * 100) if p.avg_entry > 0 else 0, 1),
                'ai_action': cached.get('action', 'NO DATA') if cached else 'NO DATA',
                'ai_confidence': cached.get('confidence', 0) if cached else 0,
                'ai_reasoning': cached.get('reasoning', '') if cached else 'No analysis yet — wait for next scan cycle',
                'ai_source': cached.get('ai_source', '') if cached else '',
                'scan_type': cached.get('scan_type', '') if cached else '',
            })
        # Enrich "NO DATA" verdicts with a helpful message
        for v in verdicts:
            if v['ai_action'] == 'NO DATA':
                v['ai_reasoning'] = 'Waiting for next scan cycle (scans run 4AM-8PM ET)'
        return jsonify({'verdicts': verdicts, 'count': len(verdicts)})
    except Exception as e:
        return jsonify({'error': str(e), 'verdicts': [], 'count': 0, 'market_closed': True,
                        'message': 'AI verdicts unavailable — positions may be empty after hours'})


# ── DECISION LOG ──────────────────────────────────────

@app.route('/api/decision-log')
@require_auth
def decision_log():
    """Complete decision history — what the bot did and WHY."""
    try:
        gw = _get_gateway()
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=100)
        orders = gw.client.get_orders(req)

        decisions = []
        for o in orders:
            if not o.filled_at:
                continue
            cid = str(o.client_order_id or '')
            strategy = 'manual'
            if 'scalp' in cid: strategy = 'Auto-Scalp (+2%)'
            elif 'runner' in cid: strategy = 'Auto-Runner (+5%)'
            elif 'trail' in cid: strategy = 'Trailing Stop'
            elif 'dip' in cid or 'quickbuy' in cid: strategy = 'Akash Method (Dip Buy)'
            elif 'protect' in cid: strategy = 'Auto-Protect'
            elif 'earnings' in cid: strategy = 'Earnings Play'
            elif 'beast' in cid: strategy = 'Beast Engine'

            decisions.append({
                'symbol': o.symbol,
                'side': o.side.value,
                'qty': str(o.filled_qty),
                'price': str(o.filled_avg_price) if o.filled_avg_price else '?',
                'time': o.filled_at.isoformat(),
                'strategy': strategy,
                'order_id': cid,
                'order_type': str(o.type.value) if o.type else '?',
            })

        decisions.sort(key=lambda x: x['time'], reverse=True)
        return jsonify({'decisions': decisions})
    except Exception as e:
        return jsonify({'error': str(e), 'decisions': []})


# ── Interactive Command Endpoints (V4) ─────────────────────────────────────

# Pending orders waiting for confirmation (in-memory, expires on restart)
_pending_orders = {}

# Global trading state
_trading_enabled = True


def _parse_command(raw: str) -> dict:
    """Parse structured commands:
    /buy NVDA 3 @210    → buy 3 shares of NVDA at $210
    /buy NVDA 3         → buy 3 shares at market
    /sell AMD 5 @350    → sell 5 shares at $350
    /sell AMD 5         → sell 5 at current price
    /cancel abc123      → cancel order by ID
    /status             → portfolio status
    /kill               → disable trading
    /resume             → re-enable trading
    """
    parts = raw.strip().split()
    if not parts:
        return {'error': 'Empty command'}

    action = parts[0].lower().lstrip('/')
    result = {'action': action, 'raw': raw}

    if action in ('buy', 'sell'):
        if len(parts) < 3:
            return {'error': f'Usage: /{action} SYMBOL QTY [@PRICE]'}
        result['symbol'] = parts[1].upper()
        try:
            result['qty'] = int(parts[2])
        except ValueError:
            return {'error': f'Invalid qty: {parts[2]}'}
        # Optional price
        if len(parts) >= 4:
            price_str = parts[3].lstrip('@$')
            try:
                result['price'] = float(price_str)
            except ValueError:
                return {'error': f'Invalid price: {parts[3]}'}
        else:
            # Use current market price
            try:
                gw = _get_gateway()
                live = gw.get_live_price(result['symbol'])
                result['price'] = round(live * (1.002 if action == 'buy' else 0.998), 2) if live else 0
            except:
                result['price'] = 0
        return result

    elif action == 'cancel':
        if len(parts) < 2:
            return {'error': 'Usage: /cancel ORDER_ID'}
        result['order_id'] = parts[1]
        return result

    elif action in ('status', 'kill', 'resume'):
        return result

    else:
        return {'error': f'Unknown command: {action}. Use /buy, /sell, /cancel, /status, /kill, /resume'}


@app.route('/api/order', methods=['POST'])
@require_auth
def execute_order():
    """Execute a trading command. Two-step: parse → preview → confirm.

    Step 1 (preview): POST with {"command": "/buy NVDA 3 @210"}
    Returns: {"preview": {"action": "buy", "symbol": "NVDA", "qty": 3, "price": 210}, "confirm_token": "abc123"}

    Step 2 (confirm): POST with {"confirm_token": "abc123"}
    Returns: {"executed": true, "order_id": "...", "message": "Bought 3 NVDA @ $210"}
    """
    auth = request.headers.get('X-API-Key', '')
    if auth != os.getenv('AI_API_KEY', 'beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}

    # Step 2: Confirm execution
    confirm_token = data.get('confirm_token')
    if confirm_token and confirm_token in _pending_orders:
        parsed = _pending_orders.pop(confirm_token)
        try:
            gw = _get_gateway()
            if parsed['action'] == 'buy':
                result = gw.quick_buy(parsed['symbol'], parsed['qty'], parsed['price'],
                                      reason=f"Dashboard command: {parsed['raw']}")
                try:
                    from db_postgres import BeastDB
                    db = BeastDB()
                    db.log_activity('BUY', symbol=parsed['symbol'], side='buy',
                                   qty=parsed['qty'], price=parsed['price'],
                                   reason=f"Dashboard: {parsed['raw']}", source='dashboard-command',
                                   order_id=result.id if result else None)
                except: pass
                return jsonify({'executed': True, 'order_id': result.id if result else None,
                               'message': f"Buy {parsed['qty']} {parsed['symbol']} @ ${parsed['price']}"})

            elif parsed['action'] == 'sell':
                result = gw.place_sell(parsed['symbol'], parsed['qty'], parsed['price'],
                                      reason=f"Dashboard command: {parsed['raw']}")
                try:
                    from db_postgres import BeastDB
                    db = BeastDB()
                    db.log_activity('SELL', symbol=parsed['symbol'], side='sell',
                                   qty=parsed['qty'], price=parsed['price'],
                                   reason=f"Dashboard: {parsed['raw']}", source='dashboard-command',
                                   order_id=result.id if result else None)
                except: pass
                return jsonify({'executed': True, 'order_id': result.id if result else None,
                               'message': f"Sell {parsed['qty']} {parsed['symbol']} @ ${parsed['price']}"})

            elif parsed['action'] == 'cancel':
                gw.client.cancel_order_by_id(parsed.get('order_id', ''))
                return jsonify({'executed': True, 'message': f"Cancelled order {parsed.get('order_id')}"})

            else:
                return jsonify({'error': f"Unknown action: {parsed['action']}"})
        except Exception as e:
            return jsonify({'error': str(e), 'executed': False})

    # Step 1: Parse and preview
    command = data.get('command', '').strip()
    if not command:
        return jsonify({'error': 'No command provided'})

    parsed = _parse_command(command)
    if 'error' in parsed:
        return jsonify(parsed)

    # Generate confirm token
    import uuid
    token = uuid.uuid4().hex[:12]
    _pending_orders[token] = parsed

    return jsonify({
        'preview': parsed,
        'confirm_token': token,
        'message': f"Preview: {parsed['action'].upper()} {parsed.get('qty','')} {parsed.get('symbol','')} @ ${parsed.get('price','market')}. Send confirm_token to execute."
    })


@app.route('/api/kill', methods=['POST'])
@require_auth
def kill_switch():
    """Emergency: disable all new orders."""
    global _trading_enabled
    auth = request.headers.get('X-API-Key', '')
    if auth != os.getenv('AI_API_KEY', 'beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c'):
        return jsonify({'error': 'Unauthorized'}), 401
    _trading_enabled = False
    try:
        from db_postgres import BeastDB
        BeastDB().log_activity('KILL', reason='Trading disabled via dashboard kill switch', source='dashboard')
    except: pass
    return jsonify({'trading_enabled': False, 'message': '🛑 KILL SWITCH ACTIVATED — all new orders blocked'})


@app.route('/api/resume', methods=['POST'])
@require_auth
def resume_trading():
    """Re-enable trading after kill switch."""
    global _trading_enabled
    auth = request.headers.get('X-API-Key', '')
    if auth != os.getenv('AI_API_KEY', 'beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c'):
        return jsonify({'error': 'Unauthorized'}), 401
    _trading_enabled = True
    try:
        from db_postgres import BeastDB
        BeastDB().log_activity('RESUME', reason='Trading re-enabled via dashboard', source='dashboard')
    except: pass
    return jsonify({'trading_enabled': True, 'message': '✅ Trading RESUMED'})


@app.route('/api/trading-status')
@require_auth
def trading_status():
    """Check if trading is enabled."""
    return jsonify({'trading_enabled': _trading_enabled})


@app.route('/api/activity-log')
@require_auth
def activity_log_pg():
    """Activity log from PostgreSQL (replaces SQLite actions)."""
    limit = request.args.get('limit', 50, type=int)
    action_type = request.args.get('type')
    symbol = request.args.get('symbol')
    try:
        from db_postgres import BeastDB
        db = BeastDB()
        activities = db.get_activity(limit=limit, action_type=action_type, symbol=symbol)
        return jsonify({'activities': activities, 'count': len(activities)})
    except Exception as e:
        return jsonify({'activities': [], 'count': 0, 'error': str(e), 'fallback': 'PostgreSQL not available'})


@app.route('/api/strategy-stats')
@require_auth
def strategy_stats():
    """P&L breakdown by strategy."""
    try:
        from db_postgres import BeastDB
        db = BeastDB()
        stats = db.get_strategy_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/live-feed')
@require_auth
def live_feed():
    """24/7 live feed — breaking news, catalysts, trade alerts, profit celebrations.
    This NEVER sleeps. Even at 3 AM, Trump could tweet something market-moving."""
    try:
        from sentiment_analyst import SentimentAnalyst
        sa = SentimentAnalyst()

        feed_items = []

        # 1. BREAKING NEWS (Google News RSS — works 24/7, no API key)
        for query, category in [
            ("stock market breaking news today", "BREAKING"),
            ("Trump tariff trade war", "TRUMP"),
            ("Federal Reserve interest rate", "FED"),
            ("Iran oil Hormuz war", "GEOPOLITICAL"),
            ("NVIDIA AMD Intel earnings", "EARNINGS"),
            ("AI artificial intelligence stocks", "AI"),
            ("bitcoin crypto", "CRYPTO"),
        ]:
            try:
                score, headlines = sa._google_news_sentiment(query)
                for h in headlines[:3]:
                    urgency = 'normal'
                    h_lower = h.lower()
                    if any(w in h_lower for w in ['crash', 'plunge', 'war', 'nuclear', 'halt', 'circuit breaker']):
                        urgency = 'critical'
                    elif any(w in h_lower for w in ['surge', 'rally', 'breakout', 'record', 'deal', 'beat']):
                        urgency = 'bullish'
                    elif any(w in h_lower for w in ['tariff', 'sanctions', 'attack', 'missile', 'crash']):
                        urgency = 'bearish'

                    feed_items.append({
                        'type': 'NEWS',
                        'category': category,
                        'headline': h,
                        'score': score,
                        'urgency': urgency,
                        'time': datetime.now(ET).isoformat(),
                    })
            except:
                pass

        # 2. YAHOO FINANCE TOP STORIES (per held stock)
        positions = []
        try:
            gw = _get_gateway()
            positions = gw.get_positions()
            import yfinance as yf
            for p in positions[:5]:
                try:
                    stock = yf.Ticker(p.symbol)
                    news = stock.news or []
                    for article in news[:2]:
                        title = ''
                        if isinstance(article, dict):
                            if 'content' in article:
                                title = article['content'].get('title', '') if isinstance(article['content'], dict) else ''
                            else:
                                title = article.get('title', '')
                        if title:
                            feed_items.append({
                                'type': 'YAHOO',
                                'category': 'STOCK_NEWS',
                                'symbol': p.symbol,
                                'headline': title,
                                'urgency': 'normal',
                                'time': datetime.now(ET).isoformat(),
                            })
                except:
                    pass
        except:
            pass

        # 3. TRADE ALERTS (recent fills from Alpaca)
        try:
            gw = _get_gateway()
            activities = gw.client.get_account_activities(activity_types=['FILL'])
            for a in (activities or [])[:10]:
                side_emoji = '🟢 BOUGHT' if a.side == 'buy' else '🔴 SOLD'

                feed_items.append({
                    'type': 'TRADE',
                    'category': 'FILL',
                    'symbol': a.symbol,
                    'headline': f"{side_emoji} {a.qty} shares of {a.symbol} @ ${a.price}",
                    'side': a.side,
                    'qty': str(a.qty),
                    'price': str(a.price),
                    'urgency': 'trade',
                    'time': a.transaction_time.isoformat() if a.transaction_time else datetime.now(ET).isoformat(),
                })
        except:
            pass

        # 4. PROFIT CELEBRATIONS (check for recent profitable sells)
        try:
            gw = _get_gateway()
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=20)
            orders = gw.client.get_orders(req)
            for o in orders:
                if o.filled_at and o.side.value == 'sell' and o.filled_avg_price:
                    cid = str(o.client_order_id or '')
                    if 'scalp' in cid or 'runner' in cid:
                        feed_items.append({
                            'type': 'CELEBRATION',
                            'category': 'PROFIT',
                            'symbol': o.symbol,
                            'headline': f"💰 PROFIT! Sold {o.filled_qty} {o.symbol} @ ${o.filled_avg_price}",
                            'urgency': 'celebration',
                            'time': o.filled_at.isoformat() if o.filled_at else '',
                            'strategy': 'Scalp' if 'scalp' in cid else 'Runner' if 'runner' in cid else 'Trade',
                        })
        except:
            pass

        # 5. CATALYST DETECTION
        catalysts = []
        try:
            for p in (positions or [])[:10]:
                info = sa.get_earnings_info(p.symbol)
                if info.get('days_until', 999) <= 3:
                    catalysts.append({
                        'type': 'CATALYST',
                        'category': 'EARNINGS',
                        'symbol': p.symbol,
                        'headline': f"⚡ {p.symbol} earnings in {info['days_until']} day(s) — {info.get('date', '?')}",
                        'urgency': 'warning',
                        'time': datetime.now(ET).isoformat(),
                    })
                short = sa.get_short_info(p.symbol)
                if short.get('squeeze_risk'):
                    catalysts.append({
                        'type': 'CATALYST',
                        'category': 'SQUEEZE',
                        'symbol': p.symbol,
                        'headline': f"🔥 {p.symbol} SHORT SQUEEZE RISK — {short['short_pct']:.1f}% short, ratio {short['short_ratio']:.1f}",
                        'urgency': 'critical',
                        'time': datetime.now(ET).isoformat(),
                    })
        except:
            pass
        feed_items.extend(catalysts)

        # Sort by time (newest first), dedupe headlines
        seen = set()
        unique = []
        for item in feed_items:
            key = item.get('headline', '')[:50]
            if key not in seen:
                seen.add(key)
                unique.append(item)

        unique.sort(key=lambda x: x.get('time', ''), reverse=True)

        return jsonify({
            'feed': unique[:30],
            'count': len(unique),
            'timestamp': datetime.now(ET).isoformat(),
        })
    except Exception as e:
        return jsonify({'feed': [], 'count': 0, 'error': str(e)})


# ══════════════════════════════════════════════════════════
#  V4 ENDPOINTS: Scan snapshots, trade log, performance,
#  notifications, bot config, bot sessions, learning
# ══════════════════════════════════════════════════════════

def _get_v4_db():
    """Get V4 DB connection (cached per-request via g)."""
    from flask import g
    if not hasattr(g, '_v4_db'):
        from db_postgres import BeastDB
        g._v4_db = BeastDB()
    return g._v4_db


@app.route('/api/v4/dashboard-state')
@require_auth
def v4_dashboard_state():
    """One-call dashboard state: session, mode, notifications, perf."""
    try:
        db = _get_v4_db()
        return jsonify(db.get_dashboard_state())
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/scan-snapshots')
@require_auth
def v4_scan_snapshots():
    """Recent scan snapshots with perf metrics (timeline view)."""
    try:
        db = _get_v4_db()
        scan_type = request.args.get('type')
        limit = int(request.args.get('limit', 20))
        return jsonify(db.get_scan_snapshots(limit=limit, scan_type=scan_type))
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/scan-detail/<scan_id>')
@require_auth
def v4_scan_detail(scan_id):
    """Full scan snapshot with all JSONB data (deep dive)."""
    try:
        db = _get_v4_db()
        return jsonify(db.get_scan_detail(scan_id))
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/trade-log')
@require_auth
def v4_trade_log():
    """Deep trade log with full context + AI reasoning."""
    try:
        db = _get_v4_db()
        symbol = request.args.get('symbol')
        side = request.args.get('side')
        limit = int(request.args.get('limit', 50))
        return jsonify(db.get_trade_log(limit=limit, symbol=symbol, side=side))
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/trade-win-rate')
@require_auth
def v4_trade_win_rate():
    """Win rate by strategy, trigger, and regime."""
    try:
        db = _get_v4_db()
        days = int(request.args.get('days', 30))
        return jsonify(db.get_trade_win_rate(days))
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/decisions')
@require_auth
def v4_decisions():
    """Trade decisions (buy/skip/block) with audit trail."""
    try:
        db = _get_v4_db()
        symbol = request.args.get('symbol')
        action = request.args.get('action')
        limit = int(request.args.get('limit', 50))
        return jsonify(db.get_decisions(limit=limit, symbol=symbol, action=action))
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/decision-accuracy')
@require_auth
def v4_decision_accuracy():
    """Were our decisions correct? Buy vs Skip accuracy."""
    try:
        db = _get_v4_db()
        days = int(request.args.get('days', 7))
        return jsonify(db.get_decision_accuracy(days))
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/missed-trades')
@require_auth
def v4_missed_trades():
    """Stocks we blocked/skipped but went up (regret analysis)."""
    try:
        db = _get_v4_db()
        days = int(request.args.get('days', 3))
        return jsonify(db.get_missed_trades(days))
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/notifications')
@require_auth
def v4_notifications():
    """Dashboard notification queue."""
    try:
        db = _get_v4_db()
        unread = request.args.get('unread', 'true').lower() == 'true'
        limit = int(request.args.get('limit', 50))
        return jsonify({
            'notifications': db.get_notifications(limit=limit, unread_only=unread),
            'unread_count': db.get_unread_count(),
        })
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/notifications/read', methods=['POST'])
@require_auth
def v4_notifications_read():
    """Mark notifications as read."""
    try:
        db = _get_v4_db()
        data = request.get_json() or {}
        ids = data.get('ids')
        db.mark_notifications_read(ids)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/config')
@require_auth
def v4_config():
    """All bot config (for settings page)."""
    try:
        db = _get_v4_db()
        category = request.args.get('category')
        return jsonify(db.get_all_config(category))
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/config', methods=['POST'])
@require_auth
def v4_config_update():
    """Update a bot config value (from dashboard)."""
    try:
        db = _get_v4_db()
        data = request.get_json() or {}
        key = data.get('key')
        value = data.get('value')
        if not key:
            return jsonify({'error': 'key required'}), 400
        db.set_config(key, value, updated_by='dashboard')
        db.invalidate_cache()
        return jsonify({'ok': True, 'key': key, 'value': value})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/kill-switch', methods=['POST'])
@require_auth
def v4_kill_switch():
    """Toggle kill switch from dashboard."""
    try:
        db = _get_v4_db()
        data = request.get_json() or {}
        enabled = data.get('enabled', True)
        db.set_config('kill_switch', enabled, updated_by='dashboard')
        db.invalidate_cache()
        db.notify('Kill Switch ' + ('ON' if enabled else 'OFF'),
                  'Kill switch toggled from dashboard', severity='warning', category='control')
        return jsonify({'ok': True, 'kill_switch': enabled})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/bot-mode', methods=['POST'])
@require_auth
def v4_bot_mode():
    """Change bot mode: active / paused / monitor_only."""
    try:
        db = _get_v4_db()
        data = request.get_json() or {}
        mode = data.get('mode', 'active')
        if mode not in ('active', 'paused', 'monitor_only'):
            return jsonify({'error': 'Invalid mode'}), 400
        db.set_config('bot_mode', mode, updated_by='dashboard')
        db.invalidate_cache()
        db.notify(f'Bot Mode → {mode.upper()}', f'Bot mode changed from dashboard', severity='info')
        return jsonify({'ok': True, 'mode': mode})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/session')
@require_auth
def v4_session():
    """Current bot session info (version, uptime, stats)."""
    try:
        db = _get_v4_db()
        return jsonify({
            'current': db.get_session_info(),
            'history': db.get_session_history(10),
        })
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/performance')
@require_auth
def v4_performance():
    """Scan performance metrics (timing breakdown)."""
    try:
        db = _get_v4_db()
        last_perf = db.get_state('last_scan_perf', {})
        # Get average scan times from recent snapshots
        snapshots = db.get_scan_snapshots(limit=20, scan_type='5min')
        avg_duration = 0
        if snapshots:
            durations = [s.get('duration_ms', 0) for s in snapshots if s.get('duration_ms')]
            avg_duration = sum(durations) // len(durations) if durations else 0
        return jsonify({
            'last_scan': last_perf,
            'avg_scan_ms': avg_duration,
            'recent_scans': snapshots[:10],
        })
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/learning/<symbol>')
@require_auth
def v4_learning(symbol):
    """Everything the bot has learned about a stock."""
    try:
        db = _get_v4_db()
        return jsonify(db.get_learning_context_for_stock(symbol.upper()))
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/daily-reports')
@require_auth
def v4_daily_reports():
    """Historical daily AI analysis reports."""
    try:
        db = _get_v4_db()
        days = int(request.args.get('days', 30))
        return jsonify(db.get_daily_reports(days))
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/price-memory')
@require_auth
def v4_price_memory():
    """All price memory (last sell, cooldowns, intraday highs)."""
    try:
        db = _get_v4_db()
        symbol = request.args.get('symbol')
        if symbol:
            return jsonify(db.get_price_memory(symbol.upper()))
        return jsonify(db.get_all_price_memory())
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/signals')
@require_auth
def v4_signals():
    """Strategy signal history (for backtesting view)."""
    try:
        db = _get_v4_db()
        symbol = request.args.get('symbol')
        strategy = request.args.get('strategy')
        hours = int(request.args.get('hours', 24))
        return jsonify(db.get_signal_history(symbol=symbol, strategy=strategy, hours=hours))
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/blue-chips')
@require_auth
def v4_blue_chips():
    """Get all blue chips."""
    try:
        db = _get_v4_db()
        return jsonify(db.get_all_blue_chips())
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/blue-chips', methods=['POST'])
@require_auth
def v4_blue_chips_add():
    """Add or update a blue chip."""
    try:
        db = _get_v4_db()
        data = request.get_json() or {}
        symbol = (data.get('symbol') or '').upper()
        if not symbol:
            return jsonify({'error': 'symbol required'}), 400
        db.add_blue_chip(
            symbol=symbol,
            name=data.get('name', ''),
            sector=data.get('sector', ''),
            tier=int(data.get('tier', 2)),
            max_loss_pct=float(data.get('max_loss_pct', -10)),
            notes=data.get('notes', ''),
            added_by='dashboard'
        )
        return jsonify({'ok': True, 'symbol': symbol})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/v4/blue-chips/<symbol>', methods=['DELETE'])
@require_auth
def v4_blue_chips_delete(symbol):
    """Remove a blue chip (soft delete)."""
    try:
        db = _get_v4_db()
        db._exec("UPDATE blue_chips SET is_active = FALSE WHERE symbol = %s", (symbol.upper(),))
        db.invalidate_cache(f"blue_{symbol.upper()}")
        db.invalidate_cache("blue_chips_set")
        return jsonify({'ok': True, 'removed': symbol.upper()})
    except Exception as e:
        return jsonify({'error': str(e)})


if __name__ == '__main__':
    print("Beast V4 Dashboard API starting on port 8080...")
    app.run(host='0.0.0.0', port=8080, debug=False)
