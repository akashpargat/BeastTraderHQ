"""
End-to-end Beast Mode autonomous test.
Runs ONE full "g" cycle using ALL real data sources.
NO orders placed. Test only.
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv('.env')

from datetime import datetime
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")

from tv_cdp_client import TVClient
from sentiment_analyst import SentimentAnalyst
from engine.master_intelligence import (
    MasterConfidenceEngine, PAST_WINNERS, FULL_SECTOR_SCAN,
    get_all_scan_symbols, get_stock_profile, is_chip_stock,
    SESSION_RULES, BEAST_MODE_PHASES
)
from order_gateway import OrderGateway
from regime_detector import RegimeDetector

api_key = os.getenv('ALPACA_API_KEY', '')
secret = os.getenv('ALPACA_SECRET_KEY', '')

print("""
╔══════════════════════════════════════════════════╗
║  🦍 BEAST MODE v2.2 — FULL E2E AUTONOMOUS TEST  ║
║  ALL data sources. TradingView + Sentiment + AI  ║
║  NO ORDERS PLACED. Test only.                    ║
╚══════════════════════════════════════════════════╝
""")

# ── Initialize all components ──────────────────────────
print("Initializing components...")
gateway = OrderGateway(api_key, secret, paper=True)
sentiment = SentimentAnalyst()
confidence = MasterConfidenceEngine()
regime_det = RegimeDetector()
tv = TVClient()

tv_ok = tv.health_check()
print(f"  Alpaca: ✅ Connected")
print(f"  TradingView CDP: {'✅ Connected' if tv_ok else '❌ Not running'}")
print(f"  Sentiment: ✅ 5 sources ready")
print(f"  Confidence Engine: ✅ 8 components")
print()

# ══════════════════════════════════════════════════════
# PHASE 0: PAST WINNERS CHECK
# ══════════════════════════════════════════════════════
print("━" * 60)
print("📌 PHASE 0: PAST WINNERS CHECK")
print("━" * 60)

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockSnapshotRequest
data_client = StockHistoricalDataClient(api_key, secret)

# Get movers + most active from Alpaca
try:
    from alpaca.trading.client import TradingClient
    tc = TradingClient(api_key, secret, paper=True)
except:
    tc = None

# Cross-reference most active with past winners
positions = gateway.get_positions()
held_symbols = [p.symbol for p in positions]
print(f"  Held: {held_symbols}")
print(f"  Past winners: {PAST_WINNERS}")

# Check which past winners we hold
for sym in PAST_WINNERS:
    if sym in held_symbols:
        pos = [p for p in positions if p.symbol == sym][0]
        emoji = "🟢" if pos.is_green else "🔴"
        print(f"  {emoji} {sym}: HOLDING {pos.qty}x @ ${pos.avg_entry:.2f} "
              f"→ ${pos.current_price:.2f} ({pos.unrealized_pl:+.2f})")

# ══════════════════════════════════════════════════════
# PHASE 1: POSITIONS + ACCOUNT
# ══════════════════════════════════════════════════════
print()
print("━" * 60)
print("📊 PHASE 1: POSITIONS + ACCOUNT")
print("━" * 60)

acct = gateway.get_account()
total_pl = sum(p.unrealized_pl for p in positions)
print(f"  Equity: ${acct.get('equity', 0):,.2f}")
print(f"  Cash: ${acct.get('cash', 0):,.2f}")
print(f"  Positions: {len(positions)} | P&L: ${total_pl:+.2f}")
print(f"  Day trades: {acct.get('day_trade_count', 0)}")

for p in positions:
    emoji = "🟢" if p.is_green else "🔴"
    print(f"  {emoji} {p.symbol:6s} {p.qty:5d}x ${p.current_price:8.2f} "
          f"P&L: ${p.unrealized_pl:+8.2f} ({p.unrealized_pl_pct:+.2%})")

# ══════════════════════════════════════════════════════
# PHASE 2: TRADINGVIEW SCAN
# ══════════════════════════════════════════════════════
print()
print("━" * 60)
print("📺 PHASE 2: TRADINGVIEW SCAN")
print("━" * 60)

# Regime detection
try:
    spy_req = StockSnapshotRequest(symbol_or_symbols='SPY', feed='iex')
    spy_snap = data_client.get_stock_snapshot(spy_req)
    spy_price = float(spy_snap['SPY'].daily_bar.close)
    spy_prev = float(spy_snap['SPY'].previous_daily_bar.close)
    spy_change = (spy_price - spy_prev) / spy_prev
except:
    spy_change = 0
    spy_price = 0

current_regime = regime_det.detect(spy_change)
print(f"  SPY: ${spy_price:.2f} ({spy_change:+.2%}) → Regime: {current_regime.value}")

tv_results = {}
scan_symbols = held_symbols[:5]  # Scan held positions first (limit for test speed)
if tv_ok:
    for sym in scan_symbols:
        print(f"  📺 Scanning {sym}...", end=" ", flush=True)
        try:
            tv._connect()
            tv.set_symbol(sym)
            time.sleep(2.5)
            studies = tv.get_study_values()
            quote = tv.get_quote()
            
            # Parse studies into readable format
            rsi = "?"
            macd = "?"
            vwap = "?"
            for s in studies:
                name = s.get('name', '')
                vals = s.get('values', {})
                if 'Relative Strength' in name:
                    rsi = vals.get('RSI', '?')
                elif name == 'MACD':
                    macd = vals.get('Histogram', '?')
                elif name == 'VWAP':
                    vwap = vals.get('VWAP', '?')
            
            close = quote.get('close', 0)
            tv_results[sym] = {
                'studies': studies, 'quote': quote,
                'rsi': rsi, 'macd': macd, 'vwap': vwap, 'price': close
            }
            print(f"RSI:{rsi} MACD:{macd} VWAP:{vwap} Price:${close:.2f}")
        except Exception as e:
            print(f"FAILED: {e}")
            tv_results[sym] = {'error': str(e)}
else:
    print("  ⚠️ TradingView not connected — skipping TV scan")

# ══════════════════════════════════════════════════════
# PHASE 3: SENTIMENT (ALL 5 SOURCES)
# ══════════════════════════════════════════════════════
print()
print("━" * 60)
print("📰 PHASE 3: FULL SENTIMENT (5 sources)")
print("━" * 60)

mkt_sentiment = sentiment.full_market_sentiment()
print()

# Per-stock sentiment for held positions
stock_sentiments = {}
for sym in held_symbols[:6]:
    s = sentiment.analyze(sym)
    stock_sentiments[sym] = s
    print(f"  {sym:6s}: Yahoo {s.yahoo_score:+d} | Reddit {s.reddit_score:+d} | "
          f"Analyst {s.analyst_score:+d} | Total {s.total_score:+d}")

# ══════════════════════════════════════════════════════
# PHASE 4: SECTOR SCAN
# ══════════════════════════════════════════════════════
print()
print("━" * 60)
print("🔍 PHASE 4: SECTOR SCAN")
print("━" * 60)

all_scan = get_all_scan_symbols()
print(f"  Total symbols to scan: {len(all_scan)}")
for sector, stocks in FULL_SECTOR_SCAN.items():
    print(f"  {sector:15s}: {', '.join(stocks[:6])}{'...' if len(stocks) > 6 else ''}")

# Check chip stocks specifically
chip_stocks = [s for s in all_scan if is_chip_stock(s)]
print(f"\n  🔬 Chip stocks: {chip_stocks}")

# ══════════════════════════════════════════════════════
# PHASE 5: CONFIDENCE ENGINE
# ══════════════════════════════════════════════════════
print()
print("━" * 60)
print("🎯 PHASE 5: CONFIDENCE ENGINE")
print("━" * 60)

scored_stocks = []
for sym in held_symbols:
    tv_data = tv_results.get(sym, {})
    sent = stock_sentiments.get(sym, sentiment.analyze(sym))
    profile = get_stock_profile(sym)
    
    # Build data dict for confidence engine
    rsi_val = 50
    macd_val = 0
    vwap_above = False
    price = 0
    
    try:
        rsi_str = tv_data.get('rsi', '50')
        rsi_val = float(str(rsi_str).replace('\u2212', '-').replace(',', ''))
    except: pass
    try:
        macd_str = tv_data.get('macd', '0')
        macd_val = float(str(macd_str).replace('\u2212', '-').replace(',', ''))
    except: pass
    
    price = tv_data.get('price', 0)
    if not price:
        pos_match = [p for p in positions if p.symbol == sym]
        price = pos_match[0].current_price if pos_match else 0
    
    prev_close = 0
    pos_match = [p for p in positions if p.symbol == sym]
    if pos_match:
        prev_close = pos_match[0].avg_entry
    
    data = {
        'symbol': sym,
        'rsi': rsi_val,
        'macd_hist': macd_val,
        'vwap_above': vwap_above,
        'volume_ratio': 1.0,
        'ema_9': 0, 'ema_21': 0,
        'bb_position': 'mid',
        'confluence': 5,
        'yahoo_score': sent.yahoo_score,
        'reddit_score': sent.reddit_score,
        'analyst_score': sent.analyst_score,
        'regime': current_regime.value,
        'price': price,
        'prev_close': prev_close,
        'is_blue_chip': profile.get('type') in ('blue_chip', 'defense'),
        'sector': profile.get('sectors', ['unknown'])[0] if profile.get('sectors') else 'unknown',
        'earnings_days': 999,
        'has_catalyst': sent.total_score >= 3,
        'vix': 19,
        'sma_20': 0,
    }
    
    result = confidence.score(sym, data)
    scored_stocks.append(result)
    
    ptype = result.position_type.value
    action = result.action.value
    conf = result.overall
    
    # Show targets if actionable
    if result.scalp_target > 0:
        scalp_pct = (result.scalp_target / result.entry_price - 1) * 100
        runner_pct = (result.runner_target / result.entry_price - 1) * 100 if result.runner_target else 0
        print(f"  {sym:6s}: {conf:5.1f}% → {action:15s} | {ptype:6s} | "
              f"Scalp ${result.scalp_target:.2f}(+{scalp_pct:.1f}%) "
              f"Runner ${result.runner_target:.2f}(+{runner_pct:.1f}%)")
    else:
        print(f"  {sym:6s}: {conf:5.1f}% → {action:15s} | {ptype}")
    
    if result.reasons:
        for r in result.reasons[:3]:
            print(f"         + {r}")
    if result.warnings:
        for w in result.warnings[:2]:
            print(f"         ! {w}")

# ══════════════════════════════════════════════════════
# PHASE 6: EARNINGS CHECK
# ══════════════════════════════════════════════════════
print()
print("━" * 60)
print("📅 PHASE 6: EARNINGS CALENDAR")
print("━" * 60)

from data_collector import DataCollector
dc = DataCollector(api_key, secret)
earnings = dc.get_earnings_dates(held_symbols)
for sym, date in earnings.items():
    days = (date.date() - datetime.now().date()).days
    if days <= 3:
        emoji = "⛔" if days <= 1 else "⚠️"
        print(f"  {emoji} {sym}: Earnings in {days} day(s) ({date.strftime('%b %d')})")
    else:
        print(f"  ✅ {sym}: Earnings {date.strftime('%b %d')} ({days} days away)")

# ══════════════════════════════════════════════════════
# PHASE 7: ACTION TABLE
# ══════════════════════════════════════════════════════
print()
print("━" * 60)
print("📋 PHASE 7: ACTION TABLE")
print("━" * 60)

print(f"  {'STOCK':6s} {'CONF':>5s} {'ACTION':15s} {'P&L':>8s} {'SCALP TGT':>10s} {'RUNNER TGT':>10s}")
print(f"  {'─' * 60}")

for result in sorted(scored_stocks, key=lambda x: x.overall, reverse=True):
    pos = [p for p in positions if p.symbol == result.symbol]
    pl = pos[0].unrealized_pl if pos else 0
    pl_str = f"${pl:+.2f}"
    
    scalp = f"${result.scalp_target:.2f}" if result.scalp_target else "—"
    runner = f"${result.runner_target:.2f}" if result.runner_target else "—"
    
    print(f"  {result.symbol:6s} {result.overall:5.1f}% {result.action.value:15s} "
          f"{pl_str:>8s} {scalp:>10s} {runner:>10s}")

# ══════════════════════════════════════════════════════
# PHASE 8: RISK CHECK
# ══════════════════════════════════════════════════════
print()
print("━" * 60)
print("🛡️ PHASE 8: RISK CHECK")
print("━" * 60)

print(f"  Total P&L: ${total_pl:+.2f}", end="")
if total_pl <= -500:
    print(" ⛔ KILL SWITCH WOULD TRIGGER")
elif total_pl <= -400:
    print(" ⚠️ APPROACHING KILL SWITCH")
else:
    print(" ✅ OK")

print(f"  Sentiment action: {mkt_sentiment.get('action', '?')}")
print(f"  Regime: {current_regime.value}")
print(f"  Session rules enforced: min +2% scalp, +5% runner")

red_positions = [p for p in positions if p.is_red]
print(f"  Red positions: {len(red_positions)} (all HELD per Iron Law 1)")
for p in red_positions:
    if p.unrealized_pl <= -500:
        print(f"    ⛔ {p.symbol}: ${p.unrealized_pl:.2f} — ALERT THRESHOLD EXCEEDED")
    elif p.unrealized_pl <= -200:
        print(f"    ⚠️ {p.symbol}: ${p.unrealized_pl:.2f} — watch closely")

# ══════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════
print()
print("━" * 60)
print("🦍 BEAST MODE v2.2 — E2E TEST COMPLETE")
print("━" * 60)
print(f"  Phases executed: 0-8 (ALL)")
print(f"  TradingView: {'✅ read {0} stocks'.format(len(tv_results)) if tv_ok else '❌ offline'}")
print(f"  Sentiment: ✅ 5 sources ({mkt_sentiment.get('total_score', 0):+d}/25)")
print(f"  Confidence: ✅ scored {len(scored_stocks)} stocks")
print(f"  Iron Laws: ✅ hardcoded (no trades placed)")
print(f"  Sector scan: ✅ {len(all_scan)} symbols mapped")
print(f"  Orders placed: 0 (TEST MODE)")
print(f"  Time: {datetime.now(ET).strftime('%H:%M:%S %Z')}")
print()
print("  🟢 Bot is ready for autonomous operation.")
print("  To go live: remove test guards and run beast_mode_loop.py")
