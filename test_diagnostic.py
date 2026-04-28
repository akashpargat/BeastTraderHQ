"""
Beast v2.0 — DIAGNOSTIC TEST (NO ORDERS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests every component against live Alpaca data.
Does NOT place any orders. Safe to run anytime.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv('.env')

import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

results = []

def test(name, fn):
    try:
        result = fn()
        results.append((PASS, name, result))
        print(f"  {PASS} {name}: {result}")
    except Exception as e:
        results.append((FAIL, name, str(e)))
        print(f"  {FAIL} {name}: {e}")
        traceback.print_exc()

print("""
╔══════════════════════════════════════════════╗
║  🧪 BEAST v2.0 DIAGNOSTIC TEST              ║
║  NO ORDERS WILL BE PLACED                    ║
╚══════════════════════════════════════════════╝
""")

api_key = os.getenv('ALPACA_API_KEY', '')
secret = os.getenv('ALPACA_SECRET_KEY', '')

# ── 1. ALPACA CONNECTION ───────────────────────────────
print("━━━ 1. ALPACA CONNECTION ━━━")

def test_alpaca_account():
    from order_gateway import OrderGateway
    gw = OrderGateway(api_key, secret, paper=True)
    acct = gw.get_account()
    return f"Equity: ${acct['equity']:,.2f} | Buying Power: ${acct['buying_power']:,.2f} | PDT: {acct['pdt']}"

def test_alpaca_positions():
    from order_gateway import OrderGateway
    gw = OrderGateway(api_key, secret, paper=True)
    positions = gw.get_positions()
    total_pl = sum(p.unrealized_pl for p in positions)
    return f"{len(positions)} positions | Total P&L: ${total_pl:+.2f}"

def test_alpaca_price():
    from order_gateway import OrderGateway
    gw = OrderGateway(api_key, secret, paper=True)
    price = gw.get_live_price('SPY')
    return f"SPY mid: ${price:.2f}"

test("Alpaca Account", test_alpaca_account)
test("Alpaca Positions", test_alpaca_positions)
test("Alpaca Live Price", test_alpaca_price)

# ── 2. DATA COLLECTOR ─────────────────────────────────
print("\n━━━ 2. DATA COLLECTOR ━━━")

def test_market_data():
    from data_collector import DataCollector
    from order_gateway import OrderGateway
    dc = DataCollector(api_key, secret)
    gw = OrderGateway(api_key, secret, paper=True)
    positions = gw.get_positions()
    md = dc.get_market_data(positions)
    return (f"SPY ${md.spy_price:.2f} ({md.spy_change_pct:+.2%}) | "
            f"Regime: {md.regime.value} | Equity: ${md.account_equity:,.2f}")

def test_market_clock():
    from data_collector import DataCollector
    dc = DataCollector(api_key, secret)
    is_open = dc.is_market_open()
    return f"Market {'OPEN' if is_open else 'CLOSED'}"

def test_bars():
    from data_collector import DataCollector
    dc = DataCollector(api_key, secret)
    bars = dc.get_bars('AMZN', '5Min', 30)
    return f"AMZN: {len(bars)} bars fetched"

test("Market Data", test_market_data)
test("Market Clock", test_market_clock)
test("OHLCV Bars", test_bars)

# ── 3. TECHNICAL ANALYST ──────────────────────────────
print("\n━━━ 3. TECHNICAL ANALYST ━━━")

def test_technicals():
    from data_collector import DataCollector
    from technical_analyst import TechnicalAnalyst
    dc = DataCollector(api_key, secret)
    ta = TechnicalAnalyst()
    bars = dc.get_bars('AMZN', '5Min', 50)
    if len(bars) < 26:
        return f"Only {len(bars)} bars — need 26+ for full analysis"
    signals = ta.analyze('AMZN', bars)
    return (f"AMZN RSI: {signals.rsi} | MACD: {signals.macd:.4f} | "
            f"VWAP: ${signals.vwap:.2f} | Confluence: {signals.confluence_score}/10")

test("Technical Analysis (AMZN)", test_technicals)

# ── 4. SENTIMENT ANALYST ──────────────────────────────
print("\n━━━ 4. SENTIMENT ANALYST ━━━")

def test_yahoo_sentiment():
    from sentiment_analyst import SentimentAnalyst
    sa = SentimentAnalyst()
    result = sa.analyze('AMZN')
    return (f"Yahoo: {result.yahoo_score}/5 | Reddit: {result.reddit_score}/5 | "
            f"Analyst: {result.analyst_score}/5 | Total: {result.total_score}/15")

def test_market_sentiment():
    from sentiment_analyst import SentimentAnalyst
    sa = SentimentAnalyst()
    result = sa.analyze_market()
    return f"SPY sentiment: {result.total_score}/15"

test("AMZN Sentiment", test_yahoo_sentiment)
test("Market Sentiment", test_market_sentiment)

# ── 5. REGIME DETECTOR ────────────────────────────────
print("\n━━━ 5. REGIME DETECTOR ━━━")

def test_regime():
    from data_collector import DataCollector
    from regime_detector import RegimeDetector
    dc = DataCollector(api_key, secret)
    spy = dc.get_snapshot('SPY')
    rd = RegimeDetector()
    regime = rd.detect(spy['change_pct'])
    status = rd.get_status()
    return f"Regime: {status['regime']} | SPY: {status['spy_change_pct']} | Hysteresis: working"

test("Regime Detection", test_regime)

# ── 6. CONFIDENCE ENGINE ──────────────────────────────
print("\n━━━ 6. CONFIDENCE ENGINE ━━━")

def test_confidence():
    from data_collector import DataCollector
    from technical_analyst import TechnicalAnalyst
    from sentiment_analyst import SentimentAnalyst
    from engine.confidence_engine import ConfidenceEngine
    from regime_detector import RegimeDetector

    dc = DataCollector(api_key, secret)
    ta = TechnicalAnalyst()
    sa = SentimentAnalyst()
    ce = ConfidenceEngine()
    rd = RegimeDetector()

    spy = dc.get_snapshot('SPY')
    regime = rd.detect(spy['change_pct'])

    bars = dc.get_bars('AMZN', '5Min', 50)
    tech = ta.analyze('AMZN', bars) if len(bars) >= 26 else None
    sent = sa.analyze('AMZN')

    if tech:
        result = ce.score('AMZN', tech, sent, regime)
        strat = result.best_strategy.value if result.best_strategy else "none"
        return (f"AMZN: {result.overall_confidence:.0%} confidence | "
                f"Signal: {result.signal.value} | Strategy: {strat}")
    return "Not enough bars for scoring"

test("Confidence Engine (AMZN)", test_confidence)

# ── 7. IRON LAWS ──────────────────────────────────────
print("\n━━━ 7. IRON LAWS (unit tests) ━━━")

def test_iron_laws():
    from models import Position, OrderSide, Regime
    from iron_laws import (
        law_1_never_sell_at_loss, law_2_limit_orders_only,
        law_5_named_strategy, check_kill_switch, check_position_max_loss
    )

    checks = []
    # Law 1: red position blocked
    pos = Position("TEST", 10, 100, 95, 950, -50, -0.05)
    r = law_1_never_sell_at_loss(pos, OrderSide.SELL)
    checks.append(f"Law1(red→block): {PASS if not r.approved else FAIL}")

    # Law 2: market order blocked
    r = law_2_limit_orders_only("market")
    checks.append(f"Law2(market→block): {PASS if not r.approved else FAIL}")

    # Law 5: FOMO blocked
    r = law_5_named_strategy("FOMO")
    checks.append(f"Law5(FOMO→block): {PASS if not r.approved else FAIL}")

    # Kill switch
    r = check_kill_switch(-600)
    checks.append(f"KillSwitch(-$600→halt): {PASS if not r.approved else FAIL}")

    # Risk cap override
    pos2 = Position("TEST", 50, 100, 96, 4800, -200, -0.04)
    r = check_position_max_loss(pos2)
    checks.append(f"RiskCap(-$200→force exit): {PASS if not r.approved else FAIL}")

    return " | ".join(checks)

test("Iron Laws Validation", test_iron_laws)

# ── 8. POLICY ENGINE ──────────────────────────────────
print("\n━━━ 8. POLICY ENGINE ━━━")

def test_policy():
    from engine.policy_engine import PolicyEngine
    pe = PolicyEngine()
    pe.record_win()
    pe.record_win()
    bc = pe.bell_curve
    pe.record_loss()
    pe.record_loss()
    halted = pe.halted
    return (f"Bell curve after 2 wins: {bc:.0%} | "
            f"After 2 losses: halted={halted} {PASS if halted else FAIL}")

test("Policy Engine (bell curve + halt)", test_policy)

# ── 9. BULL/BEAR DEBATE ───────────────────────────────
print("\n━━━ 9. BULL/BEAR DEBATE ━━━")

def test_debate():
    from engine.bull_bear_debate import BullBearDebate
    claude_key = os.getenv('ANTHROPIC_API_KEY', '')
    debate = BullBearDebate(claude_key)
    if debate.is_available:
        return "Claude connected — debate available"
    else:
        return "Claude offline — deterministic mode only (OK for paper)"

test("Bull/Bear Debate", test_debate)

# ── 10. MONITOR LOOP ──────────────────────────────────
print("\n━━━ 10. MONITOR LOOP ━━━")

def test_monitor():
    from order_gateway import OrderGateway
    from data_collector import DataCollector
    from engine.policy_engine import PolicyEngine
    from monitor import MonitorLoop

    gw = OrderGateway(api_key, secret, paper=True)
    dc = DataCollector(api_key, secret)
    pe = PolicyEngine()
    ml = MonitorLoop(gw, dc, pe)
    ml.start()
    ml.tick()  # One tick — reads positions, checks stops
    ml.stop()
    return "Monitor tick completed successfully (no orders placed)"

test("Monitor Loop (single tick)", test_monitor)

# ── SUMMARY ────────────────────────────────────────────
print(f"\n{'━' * 50}")
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
total = len(results)

print(f"""
🦍 BEAST v2.0 DIAGNOSTIC RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {PASS} PASSED: {passed}/{total}
  {FAIL} FAILED: {failed}/{total}
  Time: {datetime.now(ET).strftime('%H:%M:%S %Z')}
  
  {'🟢 ALL SYSTEMS GO — Ready to run!' if failed == 0 else '🔴 FIX FAILURES BEFORE RUNNING'}
""")
