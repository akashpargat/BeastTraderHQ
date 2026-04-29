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

    pos_data = []
    for p in positions:
        cost = p.avg_entry * p.qty
        pct = (p.unrealized_pl / cost * 100) if cost > 0 else 0
        pos_data.append({
            'symbol': p.symbol,
            'qty': p.qty,
            'avg_entry': p.avg_entry,
            'current_price': p.current_price,
            'market_value': p.market_value,
            'unrealized_pl': p.unrealized_pl,
            'pct': round(pct, 2),
            'is_green': p.unrealized_pl >= 0,
        })

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
    """Trade history with reasoning."""
    db = _get_db()
    limit = request.args.get('limit', 50, type=int)
    all_trades = db.get_all_trades(limit)
    db.close()
    return jsonify({'trades': all_trades, 'count': len(all_trades)})

@app.route('/api/trades/today')
def trades_today():
    db = _get_db()
    today = db.get_trades_today()
    db.close()
    return jsonify({'trades': today, 'count': len(today)})


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
    """Full analytics: overall, by strategy, stock, regime, day."""
    db = _get_db()
    result = {
        'overall': db.get_overall_stats(),
        'by_strategy': db.get_stats_by_strategy(),
        'by_stock': db.get_stats_by_stock(),
        'by_regime': db.get_stats_by_regime(),
        'by_day': db.get_stats_by_day(30),
        'streak': db.get_streak(),
    }
    db.close()
    return jsonify(result)


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
    """Live feed of all bot actions: trades, alerts, scans."""
    db = _get_db()
    limit = request.args.get('limit', 30, type=int)

    # Combine trades + alerts into one timeline
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

    # Merge and sort by time
    all_actions = [dict(r) for r in trades] + [dict(r) for r in alerts] + [dict(r) for r in scans]
    all_actions.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    db.close()
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
            '/api/runners', '/api/sectors', '/api/trailing-stops', '/api/news'
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
        
        return jsonify({
            'session': session,
            'runners': runners[:15],
            'timestamp': now.isoformat(),
        })
    except Exception as e:
        return jsonify({'error': str(e)})


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
        return jsonify({'error': str(e)})


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
            if o.get('type') == 'trailing_stop':
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
        return jsonify({'error': str(e)})


if __name__ == '__main__':
    print("Beast V3 Dashboard API starting on port 8080...")
    app.run(host='0.0.0.0', port=8080, debug=False)
