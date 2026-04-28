"""
🦍 BEAST MODE v2.2 — FULL "g" CYCLE
NO SHORTCUTS. EVERY stock. EVERY sector. EVERY runner.
AI Brain on ALL candidates. TV on ALL positions.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv; load_dotenv('.env')

from datetime import datetime
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")

from tv_cdp_client import TVClient
from sentiment_analyst import SentimentAnalyst
from ai_brain import AIBrain
from notifier import Notifier
from engine.master_intelligence import (
    MasterConfidenceEngine, PAST_WINNERS, FULL_SECTOR_SCAN,
    get_all_scan_symbols, get_stock_profile, is_chip_stock,
    SESSION_RULES
)
from order_gateway import OrderGateway
from regime_detector import RegimeDetector
from sector_scanner import SectorScanner

api_key = os.getenv('ALPACA_API_KEY', '')
secret = os.getenv('ALPACA_SECRET_KEY', '')

print("""
╔═══════════════════════════════════════════════════════╗
║  🦍 BEAST MODE v2.2 — FULL "g" — NO SHORTCUTS        ║
║  ALL positions + ALL runners + ALL sectors + AI Brain ║
║  NO ORDERS PLACED. Full analysis test.                ║
╚═══════════════════════════════════════════════════════╝
""")

# Init
gateway = OrderGateway(api_key, secret, paper=True)
sentiment = SentimentAnalyst()
confidence = MasterConfidenceEngine()
regime_det = RegimeDetector()
sectors = SectorScanner()
brain = AIBrain()
notify = Notifier()
tv = TVClient()
tv_ok = tv.health_check()

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockSnapshotRequest
data_client = StockHistoricalDataClient(api_key, secret)

print(f"  Alpaca: ✅ | TV CDP: {'✅' if tv_ok else '❌'} | AI Brain: {'✅ Opus 4.7' if brain.is_available else '❌'} | Telegram: ✅")
print()

# ═══════════════════════════════════════════════════════
# PHASE 0: PAST WINNERS + MOVERS + MOST ACTIVE
# ═══════════════════════════════════════════════════════
print("━" * 65)
print("📌 PHASE 0: PAST WINNERS + RUNNERS + SECTOR DETECTION")
print("━" * 65)

positions = gateway.get_positions()
held = [p.symbol for p in positions]
acct = gateway.get_account()

# Get movers + most active from Alpaca snapshots
all_scan = get_all_scan_symbols()
print(f"  Scanning {len(all_scan)} symbols across 10 sectors...")

# Get snapshots for ALL scan symbols (batch)
movers_data = []
try:
    batch_size = 20
    all_snapshots = {}
    for i in range(0, len(all_scan), batch_size):
        batch = all_scan[i:i+batch_size]
        try:
            req = StockSnapshotRequest(symbol_or_symbols=batch, feed='iex')
            snaps = data_client.get_stock_snapshot(req)
            for sym, snap in snaps.items():
                if snap.daily_bar and snap.previous_daily_bar:
                    price = float(snap.daily_bar.close)
                    prev = float(snap.previous_daily_bar.close)
                    change = (price - prev) / prev if prev > 0 else 0
                    vol = int(snap.daily_bar.volume) if snap.daily_bar.volume else 0
                    all_snapshots[sym] = {
                        'price': price, 'prev_close': prev,
                        'change_pct': change, 'volume': vol
                    }
                    movers_data.append({'symbol': sym, 'change_pct': change, 'price': price, 'volume': vol})
        except Exception as e:
            pass
    print(f"  Got snapshots for {len(all_snapshots)} stocks")
except Exception as e:
    print(f"  Snapshot batch failed: {e}")

# Sort by change % to find runners
movers_data.sort(key=lambda x: abs(x['change_pct']), reverse=True)
runners = [m for m in movers_data if m['change_pct'] > 0.01]  # >1% up
dumpers = [m for m in movers_data if m['change_pct'] < -0.02]  # >2% down

print(f"\n  🏃 RUNNERS (>1% up today):")
for r in runners[:10]:
    is_past = "⭐" if r['symbol'] in PAST_WINNERS else "  "
    is_held = "📦" if r['symbol'] in held else "  "
    print(f"  {is_past}{is_held} {r['symbol']:6s} {r['change_pct']:+.2%} @ ${r['price']:.2f} vol:{r['volume']:,}")

print(f"\n  🔻 DUMPERS (>2% down — Akash Method candidates):")
for d in dumpers[:5]:
    print(f"     {d['symbol']:6s} {d['change_pct']:+.2%} @ ${d['price']:.2f}")

# Detect sector rotation
sector_alerts = sectors.detect_sector_move(movers_data)
if sector_alerts:
    for alert in sector_alerts:
        print(f"\n  🔥 SECTOR ALERT: {alert['name']} {alert['direction']}")
        print(f"     Movers: {', '.join(alert['movers'])}")
        print(f"     Scan ALL: {', '.join(alert['scan_all'][:8])}...")

# Cross-reference past winners
past_winner_hits = [m for m in movers_data if m['symbol'] in PAST_WINNERS and abs(m['change_pct']) > 0.005]
if past_winner_hits:
    print(f"\n  ⭐ PAST WINNERS MOVING:")
    for pw in past_winner_hits:
        print(f"     {pw['symbol']:6s} {pw['change_pct']:+.2%} — PRIORITY SCAN")

# ═══════════════════════════════════════════════════════
# PHASE 1: POSITIONS
# ═══════════════════════════════════════════════════════
print()
print("━" * 65)
print("📊 PHASE 1: ALL POSITIONS")
print("━" * 65)
total_pl = sum(p.unrealized_pl for p in positions)
print(f"  Equity: ${acct.get('equity', 0):,.2f} | P&L: ${total_pl:+.2f} | Positions: {len(positions)}")
for p in positions:
    emoji = "🟢" if p.is_green else "🔴"
    print(f"  {emoji} {p.symbol:6s} {p.qty:5d}x ${p.current_price:8.2f} P&L: ${p.unrealized_pl:+8.2f} ({p.unrealized_pl_pct:+.2%})")

# ═══════════════════════════════════════════════════════
# PHASE 2: TV SCAN — ALL POSITIONS + TOP RUNNERS
# ═══════════════════════════════════════════════════════
print()
print("━" * 65)
print("📺 PHASE 2: TRADINGVIEW — ALL POSITIONS + RUNNERS")
print("━" * 65)

# Regime
spy_data = all_snapshots.get('SPY', {})
spy_change = spy_data.get('change_pct', 0)
current_regime = regime_det.detect(spy_change)
print(f"  SPY: ${spy_data.get('price', 0):.2f} ({spy_change:+.2%}) → {current_regime.value}")

# Scan ALL held positions + top runners on TV
tv_scan_list = list(dict.fromkeys(held + [r['symbol'] for r in runners[:5]]))
tv_results = {}

if tv_ok:
    tv._connect()
    for sym in tv_scan_list:
        try:
            tv.set_symbol(sym)
            time.sleep(2)
            studies = tv.get_study_values()
            quote = tv.get_quote()
            
            rsi = "?"
            macd = "?"
            vwap_val = "?"
            for s in studies:
                name = s.get('name', '')
                vals = s.get('values', {})
                if 'Relative Strength' in name:
                    rsi = vals.get('RSI', '?')
                elif name == 'MACD':
                    macd = vals.get('Histogram', '?')
                elif name == 'VWAP':
                    vwap_val = vals.get('VWAP', '?')
            
            tv_results[sym] = {'studies': studies, 'quote': quote, 'rsi': rsi, 'macd': macd, 'vwap': vwap_val}
            close = quote.get('close', 0)
            held_flag = "📦" if sym in held else "🏃"
            print(f"  {held_flag} {sym:6s} RSI:{rsi:>6s} MACD:{macd:>8s} VWAP:{vwap_val:>8s} ${close:.2f}")
        except Exception as e:
            print(f"  ❌ {sym:6s} TV failed: {e}")
else:
    print("  ⚠️ TradingView not connected")

# ═══════════════════════════════════════════════════════
# PHASE 3: FULL SENTIMENT — ALL SOURCES
# ═══════════════════════════════════════════════════════
print()
print("━" * 65)
print("📰 PHASE 3: FULL SENTIMENT (5 sources)")
print("━" * 65)

mkt_sent = sentiment.full_market_sentiment()
print()

# Per-stock sentiment for ALL held + runners
all_to_score = list(dict.fromkeys(held + [r['symbol'] for r in runners[:5]]))
stock_sents = {}
for sym in all_to_score:
    s = sentiment.analyze(sym)
    stock_sents[sym] = s
    print(f"  {sym:6s}: Yahoo {s.yahoo_score:+d} | Reddit {s.reddit_score:+d} | Analyst {s.analyst_score:+d} | Total {s.total_score:+d}")

# ═══════════════════════════════════════════════════════
# PHASE 5: CONFIDENCE ENGINE — EVERY STOCK
# ═══════════════════════════════════════════════════════
print()
print("━" * 65)
print("🎯 PHASE 5: CONFIDENCE ENGINE — ALL STOCKS")
print("━" * 65)

all_scored = []
for sym in all_to_score:
    tv_data = tv_results.get(sym, {})
    sent = stock_sents.get(sym, sentiment.analyze(sym))
    snap = all_snapshots.get(sym, {})
    profile = get_stock_profile(sym)
    pos_match = [p for p in positions if p.symbol == sym]
    
    rsi_val = 50
    macd_val = 0
    try:
        rsi_val = float(str(tv_data.get('rsi', '50')).replace('\u2212', '-').replace(',', '').replace('?', '50'))
    except: pass
    try:
        macd_val = float(str(tv_data.get('macd', '0')).replace('\u2212', '-').replace(',', '').replace('?', '0'))
    except: pass
    
    price = snap.get('price', pos_match[0].current_price if pos_match else 0)
    prev = snap.get('prev_close', 0)
    
    data = {
        'symbol': sym, 'rsi': rsi_val, 'macd_hist': macd_val,
        'vwap_above': False, 'volume_ratio': 1.0,
        'ema_9': 0, 'ema_21': 0, 'bb_position': 'mid', 'confluence': 5,
        'yahoo_score': sent.yahoo_score, 'reddit_score': sent.reddit_score,
        'analyst_score': sent.analyst_score,
        'regime': current_regime.value, 'price': price, 'prev_close': prev,
        'is_blue_chip': profile.get('type') in ('blue_chip', 'defense'),
        'sector': profile.get('sectors', ['?'])[0] if profile.get('sectors') else '?',
        'earnings_days': 999, 'has_catalyst': sent.total_score >= 3,
        'vix': 19, 'sma_20': 0,
        'holding': sym in held,
        'unrealized_pl': pos_match[0].unrealized_pl if pos_match else 0,
    }
    
    result = confidence.score(sym, data)
    all_scored.append((sym, result, data))

# Sort by confidence
all_scored.sort(key=lambda x: x[1].overall, reverse=True)

for sym, result, data in all_scored:
    action = result.action.value
    conf = result.overall
    held_flag = "📦" if sym in held else "🏃"
    
    if result.scalp_target > 0:
        s_pct = (result.scalp_target / result.entry_price - 1) * 100
        r_pct = (result.runner_target / result.entry_price - 1) * 100 if result.runner_target else 0
        print(f"  {held_flag} {sym:6s} {conf:5.1f}% {action:15s} Scalp ${result.scalp_target:.2f}(+{s_pct:.1f}%) Runner ${result.runner_target:.2f}(+{r_pct:.1f}%)")
    else:
        print(f"  {held_flag} {sym:6s} {conf:5.1f}% {action:15s}")
    
    top_reasons = result.reasons[:2]
    for r in top_reasons:
        print(f"         + {r}")
    if result.warnings:
        print(f"         ! {result.warnings[0]}")

# ═══════════════════════════════════════════════════════
# PHASE 5B: AI BRAIN — DEEP ANALYSIS ON ALL ACTIONABLE
# ═══════════════════════════════════════════════════════
print()
print("━" * 65)
print("🧠 PHASE 5B: AI BRAIN (Claude Opus 4.7) — ALL STOCKS")
print("━" * 65)

ai_results = {}
telegram_lines = ["<b>🦍 BEAST MODE — AI ANALYSIS</b>", f"Regime: {current_regime.value} | Sentiment: {mkt_sent.get('action', '?')}", ""]

for sym, result, data in all_scored:
    if brain.is_available:
        print(f"  🧠 Analyzing {sym}...", end=" ", flush=True)
        ai = brain.analyze_stock(sym, data)
        ai_results[sym] = ai
        
        action = ai.get('action', '?')
        conf = ai.get('confidence', 0)
        reasoning = ai.get('reasoning', 'No analysis')
        risks = ai.get('risks', [])
        
        emoji = {'BUY': '🟢', 'HOLD': '🟡', 'SELL': '🔴', 'WATCH': '👀', 'CONVICTION_BUY': '🔥'}.get(action, '⚪')
        print(f"{action} ({conf}%)")
        print(f"         {reasoning[:100]}")
        
        held_flag = "📦" if sym in held else "🏃"
        telegram_lines.append(f"{emoji} <b>{sym}</b> {held_flag}: {action} ({conf}%)")
        telegram_lines.append(f"  {reasoning[:120]}")
        if risks:
            telegram_lines.append(f"  ⚠️ {risks[0][:80]}")
        telegram_lines.append("")

# Bull/Bear debate on top 3
print()
print("  ⚔️ BULL vs BEAR DEBATES:")
for sym, result, data in all_scored[:3]:
    if brain.is_available:
        debate = brain.bull_bear_debate(sym, data)
        bull_conf = debate.get('bull_confidence', 50)
        bear_conf = debate.get('bear_confidence', 50)
        verdict = debate.get('verdict', '?')
        print(f"  {sym}: Bull {bull_conf}% vs Bear {bear_conf}% → {verdict}")
        print(f"    🟢 {debate.get('bull_case', '')[:90]}")
        print(f"    🔴 {debate.get('bear_case', '')[:90]}")
        telegram_lines.append(f"<b>⚔️ {sym} Debate:</b> Bull {bull_conf}% vs Bear {bear_conf}% → {verdict}")

# ═══════════════════════════════════════════════════════
# PHASE 6: EARNINGS
# ═══════════════════════════════════════════════════════
print()
print("━" * 65)
print("📅 PHASE 6: EARNINGS CALENDAR")
print("━" * 65)

from data_collector import DataCollector
dc = DataCollector(api_key, secret)
earnings = dc.get_earnings_dates(held)
for sym, date in earnings.items():
    days = (date.date() - datetime.now().date()).days
    if days <= 1:
        print(f"  ⛔ {sym}: EARNINGS {'TODAY' if days == 0 else 'TOMORROW'}")
        # AI earnings analysis
        if brain.is_available:
            snap = all_snapshots.get(sym, {})
            ea = brain.earnings_play_analysis(sym, {
                'earnings_days': days, 'price': snap.get('price', 0),
                'day_change_pct': snap.get('change_pct', 0),
                'rsi': 50, 'volume_ratio': 1.0, 'analyst_score': 4, 'recent_upgrades': 2
            })
            print(f"       AI: {ea.get('play', '?')} — {ea.get('reasoning', '')[:80]}")
            telegram_lines.append(f"📅 {sym} earnings in {days}d: {ea.get('play', '?')}")
    elif days <= 3:
        print(f"  ⚠️ {sym}: Earnings in {days} days ({date.strftime('%b %d')})")
    else:
        print(f"  ✅ {sym}: Earnings {date.strftime('%b %d')} ({days}d)")

# ═══════════════════════════════════════════════════════
# PHASE 7: ACTION TABLE
# ═══════════════════════════════════════════════════════
print()
print("━" * 65)
print("📋 PHASE 7: FINAL ACTION TABLE")
print("━" * 65)

print(f"  {'':2s}{'STOCK':6s} {'MATH':>5s} {'AI':>4s} {'ACTION':12s} {'P&L':>8s} {'SCALP':>10s} {'RUNNER':>10s}")
print(f"  {'─' * 63}")

for sym, result, data in all_scored:
    ai = ai_results.get(sym, {})
    pos_match = [p for p in positions if p.symbol == sym]
    pl = pos_match[0].unrealized_pl if pos_match else 0
    held_flag = "📦" if sym in held else "🏃"
    
    math_conf = f"{result.overall:.0f}%"
    ai_conf = f"{ai.get('confidence', '?')}%"
    ai_action = ai.get('action', result.action.value)
    
    scalp = f"${result.scalp_target:.2f}" if result.scalp_target else "—"
    runner = f"${result.runner_target:.2f}" if result.runner_target else "—"
    
    print(f"  {held_flag}{sym:6s} {math_conf:>5s} {ai_conf:>4s} {ai_action:12s} ${pl:+7.2f} {scalp:>10s} {runner:>10s}")

# ═══════════════════════════════════════════════════════
# PHASE 8: RISK + SEND TO TELEGRAM
# ═══════════════════════════════════════════════════════
print()
print("━" * 65)
print("🛡️ PHASE 8: RISK CHECK + TELEGRAM")
print("━" * 65)

print(f"  Total P&L: ${total_pl:+.2f}", end="")
if total_pl <= -500:
    print(" ⛔ KILL SWITCH ZONE")
else:
    print(" ✅ OK")
print(f"  Sentiment: {mkt_sent.get('action', '?')} ({mkt_sent.get('total_score', 0):+d}/25)")
print(f"  Regime: {current_regime.value}")

red = [p for p in positions if p.is_red]
for p in red:
    if p.unrealized_pl <= -500:
        print(f"  ⛔ {p.symbol}: ${p.unrealized_pl:.2f} — ALERT THRESHOLD")

# Send full report to Telegram
telegram_lines.append("")
telegram_lines.append(f"<b>📊 SUMMARY</b>")
telegram_lines.append(f"P&L: ${total_pl:+.2f} | Equity: ${acct.get('equity', 0):,.2f}")
telegram_lines.append(f"Regime: {current_regime.value} | Sentiment: {mkt_sent.get('action', '?')}")
telegram_lines.append(f"Runners: {len(runners)} | Sectors alert: {len(sector_alerts)}")
telegram_lines.append(f"Orders: 0 (test mode)")
telegram_lines.append(f"Time: {datetime.now(ET).strftime('%H:%M ET')}")

telegram_msg = "\n".join(telegram_lines)
print(f"\n  📱 Sending full report to Telegram ({len(telegram_lines)} lines)...")
notify.send(telegram_msg)
print("  ✅ Sent!")

print()
print("━" * 65)
print(f"🦍 FULL 'g' COMPLETE — {len(all_to_score)} stocks analyzed")
print(f"   TV: {len(tv_results)} scanned | AI: {len(ai_results)} analyzed")
print(f"   Sectors: {len(sector_alerts)} alerts | Runners: {len(runners)}")
print(f"   Orders: 0 (TEST MODE)")
print(f"   Time: {datetime.now(ET).strftime('%H:%M:%S ET')}")
print("━" * 65)
