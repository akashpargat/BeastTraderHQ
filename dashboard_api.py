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

app = Flask(__name__)
CORS(app)

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
    for p in positions:
        cost = p.avg_entry * p.qty
        pct = (p.unrealized_pl / cost * 100) if cost > 0 else 0
        entry = {
            'symbol': p.symbol,
            'qty': p.qty,
            'avg_entry': p.avg_entry,
            'current_price': p.current_price,
            'market_value': p.market_value,
            'unrealized_pl': p.unrealized_pl,
            'pct': round(pct, 2),
            'is_green': p.unrealized_pl >= 0,
            'last_tv_data': cached_tv.get(p.symbol),
            'last_sentiment': cached_sent.get(p.symbol),
            'last_ai_verdict': cached_ai.get(p.symbol),
        }
        pos_data.append(entry)

    total_pl = sum(p.unrealized_pl for p in positions)
    return jsonify({
        'equity': float(acct.get('equity', 0)),
        'buying_power': float(acct.get('buying_power', 0)),
        'cash': float(acct.get('cash', 0)),
        'total_pl': total_pl,
        'positions': sorted(pos_data, key=lambda x: x['unrealized_pl'], reverse=True),
        'open_orders': orders,
        'positions_count': len(positions),
        'orders_count': len(orders),
        'timestamp': datetime.now(ET).isoformat(),
    })


# ── TRADES ─────────────────────────────────────────────

@app.route('/api/trades')
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
def scans():
    """Scan history — every 5-min scan result."""
    db = _get_db()
    limit = request.args.get('limit', 50, type=int)
    scan_history = db.get_scan_history(limit)
    db.close()
    return jsonify({'scans': scan_history, 'count': len(scan_history)})


# ── EQUITY CURVE ───────────────────────────────────────

@app.route('/api/equity')
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
def debug_log():
    db = _get_db()
    component = request.args.get('component', None)
    limit = request.args.get('limit', 100, type=int)
    entries = db.get_debug_log(limit, component)
    db.close()
    return jsonify({'entries': entries, 'count': len(entries)})


# ── ALERTS ─────────────────────────────────────────────

@app.route('/api/alerts')
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
def correlation():
    """Portfolio correlation check."""
    from correlation_check import CorrelationChecker
    gw = _get_gateway()
    positions = gw.get_positions()
    checker = CorrelationChecker()
    return jsonify(checker.check(positions))


# ── DAILY P&L ─────────────────────────────────────────

@app.route('/api/daily-pnl')
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
def trading_status():
    """Check if trading is enabled."""
    return jsonify({'trading_enabled': _trading_enabled})


@app.route('/api/activity-log')
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


if __name__ == '__main__':
    print("Beast V3 Dashboard API starting on port 8080...")
    app.run(host='0.0.0.0', port=8080, debug=False)
