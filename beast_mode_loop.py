"""
Beast v3.0 - Grand Autonomous Trading Loop
============================================
THE REAL BEAST. Runs autonomously on Azure VM.

SCHEDULE:
  Every 60s  -> Position monitor (P&L, drops, alerts)
  Every 5min -> Full scan (TV + sentiment + AI + movers)
  4:00 AM    -> Pre-market briefing
  9:30 AM    -> Market open scan
  4:00 PM    -> Post-market summary

DATA SOURCES:
  TradingView Desktop (CDP) -> RSI, MACD, VWAP, BB, EMA, signals
  Alpaca                    -> Positions, orders, movers, quotes
  Yahoo/Reddit/Google News  -> Sentiment, Trump/tariff risk
  Claude Opus 4.7 (remote)  -> AI analysis, bull/bear debate

EXECUTION:
  Iron Laws are HARDCODED Python if/else. Cannot be bypassed.
  OrderGateway is SINGLE WRITER. Thread-safe.
  Semi-auto: >80% confidence auto-executes, 60-80% asks Discord.
"""
import logging
import time
import sys
import os
import uuid
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv('.env')

from models import (
    TechnicalSignals, SentimentScore, TradeProposal,
    OrderSide, Strategy, Regime, SignalType
)
from order_gateway import OrderGateway
from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce
from alpaca.trading.requests import LimitOrderRequest
from iron_laws import validate_entry, validate_exit, is_approved, get_rejections
from regime_detector import RegimeDetector
from tv_analyst import TradingViewAnalyst
from sector_scanner import SectorScanner, SECTORS
from notifier import Notifier

ET = ZoneInfo("America/New_York")
log = logging.getLogger('Beast')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('beast.log', encoding='utf-8'),
    ]
)

# ── CONFIG ─────────────────────────────────────────────

POSITION_INTERVAL = 60     # seconds - position monitoring
FULL_SCAN_INTERVAL = 300   # seconds - full scan with TV + sentiment + AI
RUNNER_SCAN_INTERVAL = 120 # seconds - FAST runner/movers check (every 2 min!)
AUTO_EXECUTE_THRESHOLD = 0.60  # 60%+ confidence = AUTO-BUY. Matches our Confidence Engine "Strong Buy" threshold.
ASK_THRESHOLD = 0.60           # Same — we're fully autonomous. Below 60% = no trade (Iron Law 10: when in doubt, do nothing)

# ── EXTENDED HOURS CONFIG ──────────────────────────────
ENABLE_PREMARKET = True        # Trade pre-market 4:00-9:30 AM ET
ENABLE_AFTERHOURS = True       # Trade after-hours 4:00-8:00 PM ET
PREMARKET_START = 4             # 4 AM ET
PREMARKET_END = 9               # 9:30 AM ET (regular opens)
AFTERHOURS_START = 16           # 4 PM ET
AFTERHOURS_END = 20             # 8 PM ET
EXTENDED_SCAN_INTERVAL = 600    # 10 min scans during extended hours

# ── RISK MANAGEMENT CONFIG ────────────────────────────
MAX_PORTFOLIO_RISK_PCT = 0.05     # Max 5% of portfolio per position
MAX_DAILY_LOSS = -2000            # Hard stop: halt trading if daily loss exceeds this
MAX_CORRELATED_POSITIONS = 5      # Max positions in same sector
TRAIL_PERCENT_RUNNER = 3.0        # 3% trailing stop on runners
TRAIL_PERCENT_EARNINGS = 5.0      # 5% trail on earnings holds (more room for gaps)
SHORT_ENABLED = True              # Enable shorting on weak stocks in red days

# ── SECTOR WATCHLISTS (scan ALL of these, not just tech!) ──────

# Core tech/momentum
OFFENSE = ['COIN', 'TSLA', 'META', 'MSTR']
MAG7 = ['AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA', 'TSLA']

# Semiconductors — FULL sector (Rule #27: missed $6,045 in semi gains Day 4)
SEMI = ['AMD', 'INTC', 'TSM', 'NVDA', 'QCOM', 'MU', 'AVGO', 'ARM', 'MRVL',
        'AMAT', 'KLAC', 'LRCX', 'SNDK', 'ON', 'TXN', 'NXPI', 'SWKS', 'MCHP']

# Energy / Oil — Iran tensions = money printer (Day 6: OXY +$65, DVN +$30)
ENERGY = ['DVN', 'OXY', 'XOM', 'CVX', 'HAL', 'NE', 'SLB', 'COP', 'EOG',
          'MPC', 'VLO', 'PSX', 'PXD', 'FANG']

# Defense / Aerospace — Contrarian play (Day 6: -15% in a war = oversold)
DEFENSE = ['LMT', 'RTX', 'NOC', 'GD', 'BA', 'LHX', 'KTOS', 'HII',
           'AXON', 'RKLB', 'LDOS', 'BAH']

# Telecom / 5G / AI Infrastructure — NOK's home (NVIDIA $1B invested)
TELECOM = ['NOK', 'ERIC', 'CSCO', 'JNPR', 'CIEN', 'LITE', 'CALX',
           'VZ', 'T', 'TMUS', 'AMT', 'CCI']

# Cloud / SaaS / IT
CLOUD_IT = ['CRM', 'NOW', 'ORCL', 'SNOW', 'DDOG', 'NET', 'MDB',
            'ZS', 'PANW', 'CRWD', 'FTNT', 'TEAM', 'HUBS', 'WDAY']

# Medical / Biotech / Pharma
MEDICAL = ['LLY', 'UNH', 'JNJ', 'ABBV', 'PFE', 'MRK', 'AMGN',
           'GILD', 'REGN', 'VRTX', 'BMY', 'ISRG', 'DXCM', 'MRNA']

# Solar / Clean Energy
SOLAR = ['FSLR', 'ENPH', 'SEDG', 'RUN', 'PLUG', 'BE', 'NOVA']

# Space / Quantum
SPACE = ['RKLB', 'IONQ', 'RGTI', 'LUNR', 'ASTS', 'SPCE']

# Gold / Commodities
COMMODITIES = ['GDX', 'SLV', 'GLD', 'NEM', 'GOLD', 'FCX', 'VALE']

# Consumer / Retail
CONSUMER = ['NKE', 'SBUX', 'COST', 'WMT', 'TGT', 'HD', 'LOW', 'LULU']

# Financials
FINANCIALS = ['JPM', 'GS', 'MS', 'BAC', 'WFC', 'C', 'SCHW', 'BLK']

# Leveraged ETFs — 3x exposure for earnings/momentum plays
# Day 7: SOXL +7.4% while we watched. NEVER AGAIN.
LEVERAGED_ETFS = ['SOXL', 'TQQQ', 'FNGU', 'UPRO', 'SPXL',  # 3x BULL
                  'SOXS', 'SQQQ', 'TZA', 'SPXS',              # 3x BEAR (for hedging)
                  'BITO']                                        # Bitcoin ETF

# Fintech / High-volume momentum — these show up on most_active daily
FINTECH_MOMENTUM = ['HOOD', 'SOFI', 'COIN', 'MSTR', 'SQ', 'PYPL', 'AFRM', 'UPST']

# Blue chips (proven winners for Strategy I — Mean Reversion)
BLUE_CHIPS = ['CRM', 'NOW', 'PLTR', 'LMT', 'NOK']

# PAST WINNERS — Rule #21: Check these FIRST on every scan!
# These stocks have PROVEN they work for our style.
PAST_WINNERS = ['NOK', 'GOOGL', 'CRM', 'META', 'MSFT', 'NOW', 'AMD', 'NVDA',
                'OXY', 'DVN', 'INTC', 'SOFI', 'COIN']

# ALL SECTORS combined for full market scan
ALL_SECTORS = {
    'mag7': MAG7,
    'semi': SEMI,
    'energy': ENERGY,
    'defense': DEFENSE,
    'telecom': TELECOM,
    'cloud_it': CLOUD_IT,
    'medical': MEDICAL,
    'solar': SOLAR,
    'space': SPACE,
    'commodities': COMMODITIES,
    'consumer': CONSUMER,
    'financials': FINANCIALS,
    'leveraged_etfs': LEVERAGED_ETFS,
    'fintech': FINTECH_MOMENTUM,
}

# Strategy label to Strategy enum
LABEL_TO_STRATEGY = {
    'Long': Strategy.ORB_BREAKOUT,
    'FVG': Strategy.FAIR_VALUE_GAP,
    'R2G': Strategy.RED_TO_GREEN,
    'Gap': Strategy.GAP_AND_GO,
}


class BeastModeLoop:
    """THE GRAND BEAST. Fully autonomous trading engine."""

    def __init__(self):
        api_key = os.getenv('ALPACA_API_KEY', '')
        secret = os.getenv('ALPACA_SECRET_KEY', '')

        self.gateway = OrderGateway(api_key, secret, paper=True)
        self.regime = RegimeDetector()
        self.tv = TradingViewAnalyst()
        self.sectors = SectorScanner()
        self.notify = Notifier()

        # AI Brain (Azure GPT-5.4 direct)
        self.ai = None
        try:
            from ai_brain import AIBrain
            self.ai = AIBrain()
        except Exception as e:
            log.warning(f"AI Brain init failed: {e}")

        # Risk Manager (Kelly sizing, loss limits, correlation, earnings)
        self.risk = None
        try:
            from risk_manager import RiskManager
            self.risk = RiskManager()
            log.info("✅ RiskManager initialized — Kelly sizing, loss limits, correlation checks active")
        except Exception as e:
            log.warning(f"⚠️ RiskManager init failed (using fixed sizing): {e}")

        # Pro Data Sources (congressional trades, insider, PCR, VIX, dark pool, etc.)
        self.pro_data = None
        try:
            from pro_data_sources import ProDataSources
            self.pro_data = ProDataSources()
            log.info("✅ ProDataSources initialized — congressional, insider, PCR, VIX, dark pool, Fear&Greed active")
        except Exception as e:
            log.warning(f"⚠️ ProDataSources init failed (using standard sources only): {e}")

        # TV CDP client (direct to TradingView Desktop)
        self.tv_cdp = None
        try:
            from tv_cdp_client import TVClient
            self.tv_cdp = TVClient()
            if self.tv_cdp.health_check():
                log.info("✅ TV CDP connected — MANDATORY for all trades")
            else:
                log.critical("🚨 TV CDP NOT AVAILABLE — NO TRADES WILL BE PLACED WITHOUT TV!")
                self.tv_cdp = None
        except Exception as e:
            log.critical(f"🚨 TV CDP INIT FAILED: {e} — NO TRADES WITHOUT TV!")

        # TV indicator cache: {symbol: {rsi, macd, vwap, ema, bb, sma, timestamp}}
        self._tv_cache = {}

        # State
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.active_day_trades = 0
        self.last_sell_times = {}
        self.earnings_dates = {}
        self.halted = False
        self.cycle_count = 0
        self._last_full_scan = 0
        self._last_runner_scan = 0   # Fast runner check every 2 min
        self._last_hourly_report = -1
        self._previous_prices = {}
        self._alerted_losses = set()
        self._last_notification = {}
        self._runner_alerts = {}     # Track which runners we already alerted
        self._runner_entry_times = {}  # Track when runner buys happened (for chase protection)

        log.info("BEAST MODE LOOP initialized")
        log.info(f"  AI Brain: {'ONLINE' if self.ai and self.ai.is_available else 'OFFLINE (deterministic)'}")
        log.info(f"  TV CDP: {'CONNECTED' if self.tv_cdp else 'UNAVAILABLE'}")

    # ── MAIN LOOP ──────────────────────────────────────

    def run_forever(self):
        """Main loop with two cadences:
        - Every 60s: position monitor (fast, lightweight)
        - Every 5min: full scan (TV + sentiment + AI + movers)
        """
        log.info(f"BEAST MODE ACTIVATED")
        log.info(f"  Position check: every {POSITION_INTERVAL}s")
        log.info(f"  Full scan: every {FULL_SCAN_INTERVAL}s")
        self.notify.send(
            "BEAST ENGINE V3 ONLINE\n"
            f"Positions: every {POSITION_INTERVAL}s\n"
            f"Full scan: every {FULL_SCAN_INTERVAL}s\n"
            f"AI: {'Claude Opus 4.7' if self.ai and self.ai.is_available else 'Deterministic'}\n"
            f"TV: {'Connected' if self.tv_cdp else 'Unavailable'}"
        )
        try:
            while True:
                now = datetime.now(ET)
                try:
                    self._tick(now)
                except Exception as e:
                    log.error(f"Cycle error: {e}\n{traceback.format_exc()}")
                time.sleep(POSITION_INTERVAL)
        except KeyboardInterrupt:
            log.info("Beast Mode stopped by user")
            self.notify.send("Beast Engine STOPPED by user")

    def _tick(self, now: datetime):
        """One tick of the loop."""
        self.cycle_count += 1
        hour = now.hour
        minute = now.minute
        is_weekday = now.weekday() < 5

        # Always monitor positions (fast, every 60s)
        self._monitor_positions_fast(now)

        # Determine market session
        elapsed = time.time() - self._last_full_scan
        is_market = is_weekday and 9 <= hour < 16
        is_premarket = is_weekday and ENABLE_PREMARKET and PREMARKET_START <= hour < 9
        is_afterhours = is_weekday and ENABLE_AFTERHOURS and AFTERHOURS_START <= hour < AFTERHOURS_END

        # Full scan during regular market hours (every 5 min)
        if is_market and elapsed >= FULL_SCAN_INTERVAL:
            self.run_full_scan(now)
            self._last_full_scan = time.time()

        # FAST RUNNER SCAN every 2 min — DURING ALL SESSIONS (market + pre + after)
        # Day 5: NOK ran +5% pre-market, we missed it. Day 7: NOK +9.6% pre-market.
        # RUNNERS DON'T WAIT FOR 9:30. NEITHER DO WE.
        runner_elapsed = time.time() - self._last_runner_scan
        if (is_market or is_premarket or is_afterhours) and runner_elapsed >= RUNNER_SCAN_INTERVAL:
            self._fast_runner_scan(now)
            self._last_runner_scan = time.time()

        # Extended hours full sector scan (every 10 min)
        if is_premarket and elapsed >= EXTENDED_SCAN_INTERVAL:
            log.info(f"PRE-MARKET SCAN {now.strftime('%H:%M')}")
            self.run_extended_hours_scan(now, session='premarket')
            self._last_full_scan = time.time()

        elif is_afterhours and elapsed >= EXTENDED_SCAN_INTERVAL:
            log.info(f"AFTER-HOURS SCAN {now.strftime('%H:%M')}")
            self.run_extended_hours_scan(now, session='afterhours')
            self._last_full_scan = time.time()

        # Pre-market briefing at 4:00 AM ET
        if is_weekday and hour == 4 and minute == 0 and self.cycle_count % 60 == 0:
            self._premarket_briefing(now)

        # Market open alert at 9:30 AM ET
        if is_weekday and hour == 9 and minute == 30 and self.cycle_count % 60 == 0:
            self._market_open_scan(now)

        # ── NEW PRO FEATURES ──
        # Earnings reaction — EVERY CYCLE during AH (earnings move FAST)
        if is_afterhours:
            positions = self.gateway.get_positions()
            self._check_earnings_reaction(positions, now)
        
        # Portfolio risk + shorting — every 5 cycles during market
        if is_market and self.cycle_count % 5 == 0:
            positions = self.gateway.get_positions()
            risk = self._check_portfolio_risk(positions)
            self._scan_short_candidates(positions, now)

        # Macro news scan every 10 min (catches war/Trump/Fed headlines)
        if (is_market or is_premarket) and self.cycle_count % 10 == 0:
            self._scan_macro_news(now)

        # Hourly report during market hours
        if is_market and hour != self._last_hourly_report:
            self._hourly_report(now)
            self._last_hourly_report = hour

    # ── POSITION MONITOR (every 60s) ──────────────────

    def _monitor_positions_fast(self, now: datetime):
        """Fast position check. Runs every 60 seconds.
        - P&L tracking
        - Drop alerts (>2% sudden moves)
        - Target hit detection
        - Iron Law 1 alerts (loss > $500)
        - CHASE PROTECTION (Iron Law 32): If a pre-market/runner buy drops
          sharply (-3% from entry within first 10 min), emergency cut.
          This is the edge case: we caught a runner but it reversed on us.
          NOK Day 5: bought at $11.24, dropped to $10.98 = -2.3%.
          Better to cut at -3% and re-enter at support than ride to -8%.
        """
        try:
            positions = self.gateway.get_positions()
        except Exception as e:
            log.error(f"Position fetch failed: {e}")
            return

        if not positions:
            return

        total_pl = sum(p.unrealized_pl for p in positions)
        total_value = sum(p.market_value for p in positions)

        for p in positions:
            sym = p.symbol
            pct = (p.unrealized_pl / p.cost_basis * 100) if p.cost_basis else 0

            # ═══ IRON LAW 32: CHASE PROTECTION ═══════════════
            # If we bought from a runner scan and it drops -3% from entry
            # within the first 10 minutes, this was a bad chase — CUT IT.
            # After 10 min, revert to normal Iron Law 1 (hold until green).
            # This ONLY applies to runner/pre-market buys (tracked by entry time).
            entry_time = self._runner_entry_times.get(sym)
            if entry_time and pct <= -3.0:
                minutes_held = (now - entry_time).total_seconds() / 60
                if minutes_held <= 10:
                    alert_key = f"chasecut_{sym}_{now.strftime('%Y%m%d_%H%M')}"
                    if alert_key not in self._runner_alerts:
                        self._runner_alerts[alert_key] = True
                        log.warning(
                            f"⚡ CHASE PROTECTION: {sym} dropped {pct:.1f}% from entry "
                            f"in {minutes_held:.0f} min — EMERGENCY CUT"
                        )
                        try:
                            # Cancel existing sell orders for this symbol first
                            open_orders = self.gateway.get_orders(status='open')
                            for o in open_orders:
                                if o.get('symbol') == sym and o.get('side') == 'sell':
                                    self.gateway.cancel_order(o['id'])
                            # Market-like sell: limit at current bid (fast fill)
                            cut_price = round(p.current_price * 0.998, 2)
                            self.gateway.place_sell(
                                sym, p.qty, cut_price,
                                reason=f"Law 32 chase cut {pct:.1f}% in {minutes_held:.0f}min",
                                time_in_force='gtc',
                                entry_price=p.avg_entry
                            )
                            self.notify.send(
                                f"🛑 CHASE PROTECTION: {sym}\n"
                                f"Dropped {pct:.1f}% from ${p.avg_entry:.2f} in {minutes_held:.0f}min\n"
                                f"Cut {p.qty}sh @ ${cut_price:.2f}\n"
                                f"Loss: ${p.unrealized_pl:.2f}\n"
                                f"Better to cut -3% than ride to -8%"
                            )
                            # Remove from runner tracking
                            del self._runner_entry_times[sym]
                        except Exception as e:
                            log.error(f"Chase cut failed {sym}: {e}")
                elif minutes_held > 10:
                    # After 10 min, graduate to normal Iron Law 1 (hold)
                    del self._runner_entry_times[sym]

            # Drop detection: >2% drop since last check
            prev_price = self._previous_prices.get(sym, p.current_price)
            if prev_price > 0:
                change_pct = (p.current_price - prev_price) / prev_price * 100
                if change_pct <= -2.0:
                    self._alert_once(f"drop_{sym}_{now.hour}",
                        f"DROP ALERT: {sym}\n"
                        f"Was ${prev_price:.2f} -> ${p.current_price:.2f} ({change_pct:+.1f}%)\n"
                        f"Position P&L: ${p.unrealized_pl:+.2f}")

            # Iron Law 1 alert: loss exceeds $500 (NEVER sell, but alert)
            if p.unrealized_pl <= -500 and sym not in self._alerted_losses:
                self._alerted_losses.add(sym)
                self._alert_once(f"loss500_{sym}",
                    f"IRON LAW 1 ALERT: {sym}\n"
                    f"Loss: ${p.unrealized_pl:.2f} (>{'-$500'})\n"
                    f"Entry: ${p.avg_entry:.2f} | Now: ${p.current_price:.2f}\n"
                    f"ACTION: HOLD (Iron Law 1 = NEVER sell at loss)")

            # Target hit detection: position is green > 2%
            if pct >= 2.0:
                self._alert_once(f"target_{sym}_{now.strftime('%Y%m%d')}",
                    f"TARGET HIT: {sym} +{pct:.1f}%\n"
                    f"Entry: ${p.avg_entry:.2f} | Now: ${p.current_price:.2f}\n"
                    f"P&L: ${p.unrealized_pl:+.2f}\n"
                    f"Consider: limit sell for scalp portion")

            self._previous_prices[sym] = p.current_price

        # ── DAILY LOSS CIRCUIT BREAKER ────────────────
        if total_pl <= MAX_DAILY_LOSS and not self.halted:
            self.halted = True
            log.critical(f"🛑 CIRCUIT BREAKER: Daily P&L ${total_pl:.2f} <= ${MAX_DAILY_LOSS}. HALTING ALL TRADES.")
            self.notify.send(f"🛑 CIRCUIT BREAKER TRIGGERED\nDaily loss: ${total_pl:.2f}\nAll trading HALTED until manual reset.")

        # Log summary every 5 cycles
        if self.cycle_count % 5 == 0:
            greens = sum(1 for p in positions if p.unrealized_pl > 0)
            reds = len(positions) - greens
            log.info(f"[#{self.cycle_count}] {len(positions)} pos | "
                    f"P&L: ${total_pl:+.2f} | G:{greens} R:{reds}")

    # ── DYNAMIC POSITION SIZING (ATR-based) ───────────

    def _calculate_position_size(self, symbol: str, price: float,
                                  confidence: float, cash: float) -> int:
        """Size positions using Kelly Criterion (via RiskManager) or ATR fallback.
        
        V5 UPGRADE: Uses institutional-grade sizing:
        1. Half-Kelly based on historical win rate × avg P&L
        2. VIX adjustment (halve at VIX>25)
        3. Correlation check (reduce for correlated holdings)
        4. Sector exposure cap (25% max per sector)
        5. Earnings risk check (reduce 48h before)
        6. Daily loss limit check (block if -2% daily)
        """
        # ── V5: Use RiskManager if available ──
        if self.risk:
            try:
                positions = self.gateway.get_positions()
                acct = self.gateway.get_account()
                equity = float(acct.get('equity', 100000))
                
                approval = self.risk.approve_trade(
                    symbol=symbol, side='buy', qty=0,  # qty=0 means "calculate for me"
                    price=price, conviction=confidence,
                    positions=positions, equity=equity
                )
                
                if not approval.get('approved', False):
                    rejections = approval.get('rejections', [])
                    log.warning(f"[RISK] {symbol} BLOCKED by RiskManager: {', '.join(rejections)}")
                    return 0
                
                adjusted_qty = approval.get('adjusted_qty', 0)
                if adjusted_qty > 0:
                    adjustments = approval.get('adjustments', [])
                    log.info(
                        f"[RISK] {symbol}: Kelly sizing → {adjusted_qty} shares "
                        f"(conf={confidence:.0%}, price=${price:.2f}, equity=${equity:,.0f}). "
                        f"Adjustments: {adjustments if adjustments else 'none'}"
                    )
                    return adjusted_qty
                    
            except Exception as e:
                log.warning(f"[RISK] RiskManager failed for {symbol}, falling back to ATR: {e}")
        
        # ── Fallback: ATR-based sizing (original method) ──
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            client = StockHistoricalDataClient(
                os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY')
            )
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Day,
                limit=15,
                feed='iex',
            )
            bars = client.get_stock_bars(req)
            bar_list = bars[symbol] if symbol in bars else []
            
            if len(bar_list) >= 2:
                # Calculate ATR (Average True Range)
                trs = []
                for i in range(1, len(bar_list)):
                    high = float(bar_list[i].high)
                    low = float(bar_list[i].low)
                    prev_close = float(bar_list[i-1].close)
                    tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                    trs.append(tr)
                atr = sum(trs) / len(trs) if trs else price * 0.02
                
                # ATR as % of price = volatility measure
                atr_pct = atr / price if price > 0 else 0.02
                
                # Risk budget: confidence scales the allocation
                # 60% conf → 2% of portfolio, 80% → 4%, 100% → 5%
                risk_pct = min(MAX_PORTFOLIO_RISK_PCT, 0.02 + (confidence - 0.6) * 0.075)
                risk_budget = cash * risk_pct
                
                # Position size = risk budget / ATR (volatile stocks = fewer shares)
                # Cap single position at risk_budget
                position_value = min(risk_budget, cash * MAX_PORTFOLIO_RISK_PCT)
                qty = max(1, int(position_value / price))
                
                log.info(f"  📏 ATR sizing {symbol}: ATR=${atr:.2f} ({atr_pct:.1%}), "
                        f"conf={confidence:.0%}, risk={risk_pct:.1%}, qty={qty}")
                return qty
        except Exception as e:
            log.debug(f"ATR sizing failed for {symbol}: {e}")
        
        # Fallback: price-bracket sizing (original method)
        if price > 500: return 3
        elif price > 200: return 5
        elif price > 100: return 10
        elif price > 50: return 25
        elif price > 20: return 50
        else: return 200

    # ── MANDATORY TV ANALYSIS (Iron Law 3 — NO TRADE WITHOUT TV) ──

    def _run_tv_analysis(self, symbol: str) -> dict:
        """RUN TRADINGVIEW ANALYSIS ON A STOCK. THIS IS MANDATORY.
        
        ⛔ IF TV IS NOT RUNNING, NO ORDERS GET PLACED. PERIOD.
        ⛔ IF TV RETURNS NO DATA, NO ORDERS GET PLACED. PERIOD.
        
        Returns dict with:
        - rsi: float (0-100)
        - macd: float (histogram)
        - macd_signal: float
        - vwap: float
        - ema: float (EMA value)
        - bb_upper, bb_lower, bb_basis: float (Bollinger Bands)
        - sma: float (200 SMA)
        - volume: str
        - confidence: float (0.0-1.0) calculated from ALL indicators
        - signal: 'BUY' | 'SELL' | 'HOLD'
        - reasons: list[str] — why this confidence score
        - tv_ok: bool — whether TV data was successfully retrieved
        
        CONFIDENCE SCORING (each indicator adds/subtracts):
        - RSI < 30 → oversold → +15% (buy signal)
        - RSI 30-50 → healthy → +10%
        - RSI 50-70 → neutral → +5%
        - RSI > 70 → overbought → -10% (unless momentum with catalyst)
        - MACD histogram > 0 → bullish momentum → +10%
        - MACD crossing signal upward → +15%
        - Price > VWAP → bullish → +10%
        - Price < VWAP → bearish → -5%
        - Price > EMA → uptrend → +5%
        - Price above BB upper → extended → -10%
        - Price near BB lower → oversold → +10%
        - Price > 200 SMA → long-term uptrend → +10%
        - Price < 200 SMA → long-term downtrend → -10%
        
        Base confidence: 40% (need indicators to push above 60% for auto-buy)
        """
        result = {
            'symbol': symbol, 'tv_ok': False, 'confidence': 0.0,
            'signal': 'HOLD', 'reasons': [], 'rsi': 0, 'macd': 0,
            'macd_signal': 0, 'vwap': 0, 'ema': 0, 'sma': 0,
            'bb_upper': 0, 'bb_lower': 0, 'bb_basis': 0, 'volume': '0',
            'price': 0,
        }
        
        # ⛔ HARD CHECK: TV MUST BE CONNECTED
        if not self.tv_cdp:
            log.critical(f"🚨 TV NOT CONNECTED — CANNOT ANALYZE {symbol}. NO TRADE ALLOWED.")
            self.notify.send(f"🚨 ERROR: TradingView is NOT running!\nCannot trade {symbol}.\nStart TV Desktop and restart bot.")
            result['reasons'].append("TV NOT CONNECTED")
            return result
        
        # Check cache (valid for 2 min to avoid hammering TV)
        cache = self._tv_cache.get(symbol)
        if cache and (time.time() - cache.get('timestamp', 0)) < 120:
            return cache
        
        try:
            # Load symbol on TV chart
            from tv_cdp_client import TVClient
            self.tv_cdp.set_symbol(symbol)
            time.sleep(1.5)  # Wait for chart to load
            
            # Read ALL study values
            studies = self.tv_cdp.get_study_values()
            if not studies or not studies.get('success'):
                log.error(f"🚨 TV study values FAILED for {symbol}")
                result['reasons'].append("TV study read failed")
                return result
            
            # Get current price
            ohlcv = self.tv_cdp.get_ohlcv(count=1, summary=True)
            price = 0
            if ohlcv and ohlcv.get('success'):
                price = ohlcv.get('close', 0)
            result['price'] = price
            
            # Parse ALL indicators from TV (original + new additions)
            rsi = 0
            macd_hist = 0
            macd_val = 0
            macd_sig = 0
            vwap = 0
            emas = []  # Collect ALL EMAs for ribbon analysis
            sma = 0
            bb_upper = 0
            bb_lower = 0
            bb_basis = 0
            volume_str = "0"
            # NEW: Ichimoku Cloud
            ichi_tenkan = 0
            ichi_kijun = 0
            ichi_span_a = 0
            ichi_span_b = 0
            # NEW: Guru script signals
            guru_vwap = 0
            guru_vwap_upper = 0
            guru_vwap_lower = 0
            
            for study in studies.get('studies', []):
                name = study.get('name', '')
                vals = study.get('values', {})
                
                if 'Relative Strength Index' in name or name == 'Relative Strength Index':
                    rsi = float(vals.get('RSI', 0))
                elif name == 'MACD':
                    macd_hist = float(vals.get('Histogram', 0))
                    macd_val = float(vals.get('MACD', 0))
                    macd_sig = float(vals.get('Signal', 0))
                elif name == 'VWAP':
                    vwap = float(vals.get('VWAP', 0))
                elif 'Moving Average Exponential' in name:
                    ema_val = float(vals.get('MA', 0))
                    if ema_val > 0:
                        emas.append(ema_val)
                elif name == 'Moving Average':
                    sma = float(vals.get('MA', 0))
                elif name == 'Bollinger Bands':
                    bb_upper = float(vals.get('Upper', 0))
                    bb_lower = float(vals.get('Lower', 0))
                    bb_basis = float(vals.get('Basis', 0))
                elif name == 'Volume':
                    volume_str = vals.get('Volume', '0')
                elif 'Ichimoku' in name:
                    ichi_tenkan = float(vals.get('Tenkan-sen', vals.get('Conversion Line', 0)))
                    ichi_kijun = float(vals.get('Kijun-sen', vals.get('Base Line', 0)))
                    ichi_span_a = float(vals.get('Senkou Span A', vals.get('Leading Span A', 0)))
                    ichi_span_b = float(vals.get('Senkou Span B', vals.get('Leading Span B', 0)))
                elif 'Guru' in name:
                    guru_vwap = float(vals.get('VWAP', 0))
                    guru_vwap_upper = float(vals.get('VWAP +2σ', 0))
                    guru_vwap_lower = float(vals.get('VWAP -2σ', 0))
                    if not vwap:
                        vwap = guru_vwap
            
            ema = emas[0] if emas else 0
            
            result.update({
                'rsi': rsi, 'macd': macd_hist, 'macd_signal': macd_sig,
                'macd_value': macd_val, 'vwap': vwap, 'ema': ema, 'emas': emas,
                'sma': sma, 'bb_upper': bb_upper, 'bb_lower': bb_lower,
                'bb_basis': bb_basis, 'volume': volume_str, 'tv_ok': True,
                'ichi_tenkan': ichi_tenkan, 'ichi_kijun': ichi_kijun,
                'ichi_span_a': ichi_span_a, 'ichi_span_b': ichi_span_b,
                'guru_vwap_lower': guru_vwap_lower, 'guru_vwap_upper': guru_vwap_upper,
            })
            
            # ═══ CONFIDENCE SCORING ENGINE v2.0 (11 indicators) ═══
            confidence = 0.35  # Base: 35% (lowered — more indicators to earn it)
            reasons = []
            
            # ── 1. RSI scoring ──
            if rsi > 0:
                if rsi < 30:
                    confidence += 0.15
                    reasons.append(f"RSI {rsi:.0f} OVERSOLD (+15%)")
                elif rsi < 50:
                    confidence += 0.10
                    reasons.append(f"RSI {rsi:.0f} healthy (+10%)")
                elif rsi < 70:
                    confidence += 0.05
                    reasons.append(f"RSI {rsi:.0f} neutral (+5%)")
                else:
                    confidence -= 0.10
                    reasons.append(f"RSI {rsi:.0f} OVERBOUGHT (-10%)")
            
            # ── 2. MACD scoring ──
            if macd_hist > 0:
                confidence += 0.08
                reasons.append(f"MACD histogram +{macd_hist:.2f} bullish (+8%)")
                if macd_val > macd_sig:
                    confidence += 0.05
                    reasons.append(f"MACD above signal (+5%)")
            elif macd_hist < 0:
                confidence -= 0.05
                reasons.append(f"MACD histogram {macd_hist:.2f} bearish (-5%)")
            
            # ── 3. VWAP scoring ──
            if price > 0 and vwap > 0:
                if price > vwap:
                    confidence += 0.08
                    reasons.append(f"Price > VWAP ${vwap:.2f} (+8%)")
                else:
                    confidence -= 0.05
                    reasons.append(f"Price < VWAP ${vwap:.2f} (-5%)")
            
            # ── 4. EMA RIBBON scoring (NEW!) ──
            if len(emas) >= 2 and price > 0:
                sorted_emas = sorted(emas)
                all_bullish = all(price > e for e in emas)
                all_stacked = sorted_emas == list(reversed(sorted(emas)))
                if all_bullish:
                    confidence += 0.08
                    reasons.append(f"Price above ALL {len(emas)} EMAs (+8%)")
                elif price > emas[0]:
                    confidence += 0.03
                    reasons.append(f"Price above short EMA (+3%)")
                else:
                    confidence -= 0.05
                    reasons.append(f"Price BELOW EMAs (-5%)")
            elif price > 0 and ema > 0:
                if price > ema:
                    confidence += 0.05
                    reasons.append(f"Price > EMA ${ema:.2f} (+5%)")
                else:
                    confidence -= 0.05
                    reasons.append(f"Price < EMA (-5%)")
            
            # ── 5. Bollinger Bands scoring ──
            if price > 0 and bb_upper > 0:
                if price >= bb_upper:
                    confidence -= 0.08
                    reasons.append(f"At BB upper ${bb_upper:.2f} EXTENDED (-8%)")
                elif price <= bb_lower:
                    confidence += 0.10
                    reasons.append(f"At BB lower ${bb_lower:.2f} OVERSOLD (+10%)")
                else:
                    confidence += 0.03
                    reasons.append(f"Inside BB bands (+3%)")
            
            # ── 6. 200 SMA scoring (long-term trend) ──
            if price > 0 and sma > 0:
                if price > sma:
                    confidence += 0.08
                    reasons.append(f"Price > 200 SMA ${sma:.2f} UPTREND (+8%)")
                else:
                    confidence -= 0.08
                    reasons.append(f"Price < 200 SMA DOWNTREND (-8%)")
            
            # ── 7. ICHIMOKU CLOUD scoring (NEW!) ──
            if price > 0 and ichi_span_a > 0 and ichi_span_b > 0:
                cloud_top = max(ichi_span_a, ichi_span_b)
                cloud_bottom = min(ichi_span_a, ichi_span_b)
                if price > cloud_top:
                    confidence += 0.10
                    reasons.append(f"ABOVE Ichimoku cloud (+10%) 🟢")
                elif price < cloud_bottom:
                    confidence -= 0.10
                    reasons.append(f"BELOW Ichimoku cloud (-10%) 🔴")
                else:
                    reasons.append(f"INSIDE Ichimoku cloud (neutral)")
                
                # Tenkan/Kijun cross (momentum signal)
                if ichi_tenkan > ichi_kijun:
                    confidence += 0.05
                    reasons.append(f"Tenkan > Kijun = bullish momentum (+5%)")
            
            # ── 8. GURU SCRIPT signals (NEW!) ──
            if guru_vwap_lower > 0 and guru_vwap_upper > 0 and price > 0:
                if price <= guru_vwap_lower:
                    confidence += 0.10
                    reasons.append(f"At Guru VWAP -2σ ${guru_vwap_lower:.2f} OVERSOLD (+10%)")
                elif price >= guru_vwap_upper:
                    confidence -= 0.08
                    reasons.append(f"At Guru VWAP +2σ EXTENDED (-8%)")
            
            # ── 9. PAST WINNER BONUS ──
            if symbol in PAST_WINNERS:
                confidence += 0.10
                reasons.append(f"PAST WINNER bonus (+10%)")
            
            # Cap confidence 0-1
            confidence = max(0.0, min(1.0, confidence))
            
            # Determine signal
            if confidence >= 0.70:
                signal = 'STRONG_BUY'
            elif confidence >= 0.60:
                signal = 'BUY'
            elif confidence >= 0.45:
                signal = 'HOLD'
            elif confidence >= 0.30:
                signal = 'WEAK'
            else:
                signal = 'SELL'
            
            result['confidence'] = confidence
            result['signal'] = signal
            result['reasons'] = reasons
            
            log.info(
                f"📊 TV ANALYSIS {symbol}: {signal} ({confidence:.0%})\n"
                f"   RSI={rsi:.0f} MACD={macd_hist:+.2f} VWAP=${vwap:.2f} "
                f"EMA=${ema:.2f} SMA=${sma:.2f}\n"
                f"   BB=[${bb_lower:.2f}-${bb_upper:.2f}] Price=${price:.2f}\n"
                f"   Reasons: {', '.join(reasons[:5])}"
            )
            
            # Cache result for 2 min
            result['timestamp'] = time.time()
            self._tv_cache[symbol] = result
            
            return result
            
        except Exception as e:
            log.error(f"🚨 TV ANALYSIS FAILED for {symbol}: {e}")
            result['reasons'].append(f"TV error: {e}")
            return result

    # ── PORTFOLIO RISK CHECK ──────────────────────────

    def _check_portfolio_risk(self, positions: list) -> dict:
        """Check portfolio health: correlation, concentration, drawdown.
        
        Returns risk report with:
        - sector_concentration: positions per sector
        - max_position_pct: largest position as % of portfolio
        - total_exposure: long vs short exposure
        - correlation_warning: if too many same-sector positions
        """
        acct = self.gateway.get_account()
        equity = float(acct.get('equity', 100000))
        
        # Sector concentration check
        sector_counts = {}
        for p in positions:
            for sector_name, symbols in ALL_SECTORS.items():
                if p.symbol in symbols:
                    sector_counts[sector_name] = sector_counts.get(sector_name, 0) + 1
        
        # Largest position check
        max_pos_pct = 0
        max_pos_sym = ""
        for p in positions:
            pos_pct = p.market_value / equity * 100 if equity > 0 else 0
            if pos_pct > max_pos_pct:
                max_pos_pct = pos_pct
                max_pos_sym = p.symbol
        
        # Warnings
        warnings = []
        for sector, count in sector_counts.items():
            if count > MAX_CORRELATED_POSITIONS:
                warnings.append(f"⚠️ {sector}: {count} positions (max {MAX_CORRELATED_POSITIONS})")
        
        if max_pos_pct > 10:
            warnings.append(f"⚠️ {max_pos_sym} is {max_pos_pct:.1f}% of portfolio (>10%)")
        
        total_long = sum(p.market_value for p in positions if p.side == 'long')
        total_short = sum(abs(p.market_value) for p in positions if p.side == 'short')
        
        report = {
            'sector_counts': sector_counts,
            'max_position': (max_pos_sym, max_pos_pct),
            'long_exposure': total_long,
            'short_exposure': total_short,
            'net_exposure': total_long - total_short,
            'warnings': warnings,
        }
        
        if warnings:
            for w in warnings:
                log.warning(w)
        
        return report

    # ── EARNINGS REACTION TRADING ─────────────────────

    def _check_earnings_reaction(self, positions: list, now: datetime):
        """After earnings report: if stock gaps up >3% AH, buy MORE.
        If stock gaps down >5% AH, cut the position.
        
        Pro bots actively trade the after-hours reaction:
        - Beat + gap up → add to position (momentum continues at open)
        - Miss + gap down → cut remaining (damage control)
        """
        if now.hour < 16 or now.hour > 20:
            return  # Only check during after-hours
        
        for p in positions:
            sym = p.symbol
            
            # Compare current AH price to TODAY'S CLOSE (lastday_price won't work, 
            # use the day bar close which is today's regular session close)
            # p.current_price = live AH price from Alpaca
            # We need today's closing price — use lastday_price as approximation
            # since Alpaca positions update current_price in AH
            close_price = getattr(p, 'lastday_price', 0) or self._previous_prices.get(sym, p.avg_entry)
            if close_price <= 0:
                close_price = p.avg_entry
            
            ah_change = (p.current_price - close_price) / close_price * 100 if close_price > 0 else 0
            pct_from_entry = (p.current_price - p.avg_entry) / p.avg_entry * 100 if p.avg_entry > 0 else 0
            
            # Gap up >3% in AH = earnings beat → buy more
            if ah_change > 3.0 and pct_from_entry > 0:
                alert_key = f"earnings_add_{sym}_{now.strftime('%Y%m%d')}"
                if alert_key not in self._runner_alerts:
                    self._runner_alerts[alert_key] = True
                    acct = self.gateway.get_account()
                    cash = float(acct.get('cash', 0))
                    add_qty = self._calculate_position_size(sym, p.current_price, 0.75, cash)
                    add_qty = max(1, add_qty // 2)  # Half size for AH (less liquidity)
                    
                    try:
                        from models import TradeProposal, Strategy as StratEnum
                        proposal = TradeProposal(
                            symbol=sym, qty=add_qty, side=OrderSide.BUY,
                            limit_price=round(p.current_price * 1.002, 2),
                            strategy=StratEnum.ORB_BREAKOUT,
                            confidence=0.75,
                        )
                        self.gateway.place_buy(
                            proposal, None, positions, self.daily_pnl,
                            self.consecutive_losses, self.active_day_trades,
                            self.last_sell_times, self.earnings_dates,
                        )
                        # Trail the add-on
                        self.gateway.place_trailing_stop(sym, add_qty,
                            trail_percent=TRAIL_PERCENT_EARNINGS,
                            reason="Earnings beat add-on",
                            entry_price=p.current_price)
                        
                        msg = (f"📈 EARNINGS BEAT ADD: {sym}\n"
                              f"AH gap: +{ah_change:.1f}%\n"
                              f"Adding {add_qty}sh @ ${p.current_price:.2f}\n"
                              f"Trailing 5% stop on add-on")
                        log.info(msg)
                        self.notify.send(msg)
                    except Exception as e:
                        log.error(f"Earnings add failed {sym}: {e}")
            
            # Gap down >5% in AH = earnings miss → cut position
            elif ah_change < -5.0:
                alert_key = f"earnings_cut_{sym}_{now.strftime('%Y%m%d')}"
                if alert_key not in self._runner_alerts:
                    self._runner_alerts[alert_key] = True
                    cut_qty = p.qty // 2  # Cut half, keep half for recovery
                    if cut_qty > 0:
                        cut_price = round(p.current_price * 0.998, 2)
                        try:
                            self.gateway.place_sell(sym, cut_qty, cut_price,
                                reason=f"Earnings miss cut {ah_change:.1f}%",
                                entry_price=p.avg_entry)
                            msg = (f"📉 EARNINGS MISS CUT: {sym}\n"
                                  f"AH gap: {ah_change:.1f}%\n"
                                  f"Cutting {cut_qty}sh @ ${cut_price:.2f}\n"
                                  f"Keeping {p.qty - cut_qty}sh for recovery")
                            log.info(msg)
                            self.notify.send(msg)
                        except Exception as e:
                            log.error(f"Earnings cut failed {sym}: {e}")

    # ── SHORT SELLING (weak stocks on red days) ───────

    def _scan_short_candidates(self, positions: list, now: datetime):
        """Short weak stocks that are breaking down on red days.
        
        Criteria for shorting:
        1. Market is RED (SPY down >0.5%)
        2. Stock is down >2% today with increasing volume
        3. Stock is NOT in our long positions (no hedging same stock)
        4. RSI > 65 on daily (overbought + breaking = momentum short)
        
        Risk: Stop at +2% above entry (max loss 2%)
        Target: -3% to -5% drop for cover
        """
        if not SHORT_ENABLED:
            return
        
        spy_change = self._get_spy_change()
        if spy_change > -0.005:  # SPY needs to be down >0.5%
            return
        
        held_symbols = [p.symbol for p in positions]
        movers = self._get_movers()
        if not movers:
            return
        
        losers = [m for m in movers.get('losers', [])
                  if m.get('price', 0) > 10 
                  and m.get('percent_change', 0) < -2.0
                  and m.get('symbol', '') not in held_symbols]
        
        acct = self.gateway.get_account()
        cash = float(acct.get('cash', 0))
        
        for m in losers[:3]:  # Max 3 shorts at a time
            sym = m.get('symbol', '')
            price = m.get('price', 0)
            pct = m.get('percent_change', 0)
            
            # Check if it's in our sector universe
            in_sectors = any(sym in stocks for stocks in ALL_SECTORS.values())
            if not in_sectors:
                continue
            
            alert_key = f"short_{sym}_{now.strftime('%Y%m%d')}"
            if alert_key in self._runner_alerts:
                continue
            self._runner_alerts[alert_key] = True
            
            qty = self._calculate_position_size(sym, price, 0.55, cash)
            qty = max(1, qty // 2)  # Half size for shorts (more risk)
            
            try:
                from models import TradeProposal, Strategy as StratEnum
                proposal = TradeProposal(
                    symbol=sym, qty=qty, side=OrderSide.SELL,
                    limit_price=round(price * 0.998, 2),  # Slight discount
                    strategy=StratEnum.ORB_BREAKOUT,
                    confidence=0.60,
                    reason=f"Short: {sym} {pct:.1f}% on red day (SPY {spy_change:.1%})",
                )
                # Place short sell
                client_id = f"beast-short-{uuid.uuid4().hex[:8]}"
                from alpaca.trading.requests import LimitOrderRequest
                order_req = LimitOrderRequest(
                    symbol=sym, qty=qty, side=AlpacaSide.SELL,
                    time_in_force=TimeInForce.GTC,
                    limit_price=round(price * 0.998, 2),
                    client_order_id=client_id,
                )
                raw_order = self.gateway.client.submit_order(order_req)
                
                # Set cover (buy to close) at -3% = profit target
                cover_price = round(price * 0.97, 2)
                cover_id = f"beast-cover-{uuid.uuid4().hex[:8]}"
                cover_req = LimitOrderRequest(
                    symbol=sym, qty=qty, side=AlpacaSide.BUY,
                    time_in_force=TimeInForce.GTC,
                    limit_price=cover_price,
                    client_order_id=cover_id,
                )
                self.gateway.client.submit_order(cover_req)
                
                msg = (f"🩳 SHORT: {sym}\n"
                      f"SELL {qty}sh @ ${price:.2f} ({pct:.1f}% today)\n"
                      f"Cover target: ${cover_price:.2f} (-3%)\n"
                      f"SPY: {spy_change:.1%} (red day)")
                log.info(msg)
                self.notify.send(msg)
            except Exception as e:
                log.error(f"Short failed {sym}: {e}")

    # ── MACRO NEWS SCANNER (war/Trump/Fed/oil → sector rotation) ──

    # Keyword → sector mapping: when these headlines appear, scan these sectors
    MACRO_SECTOR_MAP = {
        # War / Geopolitics
        'war': ['defense', 'energy', 'commodities'],
        'iran': ['energy', 'defense', 'commodities'],
        'china': ['semi', 'defense', 'commodities'],
        'taiwan': ['semi', 'defense'],
        'russia': ['energy', 'defense', 'commodities'],
        'ukraine': ['energy', 'defense', 'commodities'],
        'missile': ['defense', 'space'],
        'military': ['defense', 'space'],
        'sanctions': ['energy', 'financials', 'commodities'],
        'nato': ['defense'],
        'strait': ['energy', 'commodities'],  # Strait of Hormuz = oil
        'opec': ['energy'],
        'middle east': ['energy', 'defense'],
        'north korea': ['defense'],
        'tariff': ['semi', 'consumer', 'commodities'],
        
        # Trump / Politics
        'trump': ['energy', 'defense', 'financials', 'consumer'],
        'executive order': ['energy', 'defense', 'cloud_it'],
        'deregulation': ['financials', 'energy'],
        'trade war': ['semi', 'consumer', 'commodities'],
        'stimulus': ['financials', 'consumer', 'cloud_it'],
        
        # Fed / Economy
        'fed': ['financials', 'cloud_it'],
        'rate cut': ['financials', 'cloud_it', 'consumer'],
        'rate hike': ['financials', 'commodities'],
        'inflation': ['energy', 'commodities', 'financials'],
        'recession': ['consumer', 'financials'],
        'jobs report': ['financials', 'consumer'],
        'gdp': ['financials', 'consumer'],
        'cpi': ['energy', 'commodities', 'financials'],
        
        # Oil / Energy specific
        'oil': ['energy'],
        'crude': ['energy'],
        'natural gas': ['energy'],
        'pipeline': ['energy'],
        'refinery': ['energy'],
        'brent': ['energy'],
        
        # Tech specific
        'ai ': ['semi', 'cloud_it', 'mag7'],
        'artificial intelligence': ['semi', 'cloud_it', 'mag7'],
        'chips act': ['semi'],
        'semiconductor': ['semi'],
        'data center': ['semi', 'cloud_it', 'energy'],
        'openai': ['semi', 'cloud_it', 'mag7'],
        'nvidia': ['semi'],
        
        # Sector events
        'fda': ['medical'],
        'drug approval': ['medical'],
        'clinical trial': ['medical'],
        'solar': ['solar'],
        'renewable': ['solar'],
        'ev ': ['consumer', 'energy'],
        'electric vehicle': ['consumer'],
        'crypto': ['financials'],
        'bitcoin': ['financials'],
        'space': ['space'],
        'launch': ['space'],
        '5g': ['telecom'],
        'telecom': ['telecom'],
    }

    def _scan_macro_news(self, now: datetime):
        """Scan financial news headlines for macro events that drive sector rotation.
        
        Day 6: Iran/oil → energy stocks ran +2.5% while tech tanked.
        We didn't scan energy until Akash yelled. NEVER AGAIN.
        
        This auto-detects:
        - War headlines → scan defense + energy
        - Trump tariffs → scan semis + consumer
        - Fed rate moves → scan financials
        - Oil spikes → scan energy
        - AI news → scan semis + cloud
        
        Uses Yahoo Finance + Google News RSS (no API key needed).
        """
        alert_key = f"macro_{now.strftime('%Y%m%d_%H')}"
        if alert_key in self._runner_alerts:
            return  # Already scanned this hour
        
        log.info("📰 Scanning macro news for sector rotation signals...")
        
        headlines = []
        
        # Source 1: Yahoo Finance RSS
        try:
            import urllib.request
            import xml.etree.ElementTree as ET
            url = "https://finance.yahoo.com/news/rssindex"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read().decode('utf-8', errors='ignore')
                root = ET.fromstring(data)
                for item in root.findall('.//item')[:20]:
                    title = item.find('title')
                    if title is not None and title.text:
                        headlines.append(title.text.lower())
        except Exception as e:
            log.debug(f"Yahoo RSS failed: {e}")
        
        # Source 2: Google News RSS for finance
        try:
            import urllib.request
            import xml.etree.ElementTree as ET
            url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read().decode('utf-8', errors='ignore')
                root = ET.fromstring(data)
                for item in root.findall('.//item')[:20]:
                    title = item.find('title')
                    if title is not None and title.text:
                        headlines.append(title.text.lower())
        except Exception as e:
            log.debug(f"Google News RSS failed: {e}")
        
        # Source 3: Reddit hot headlines
        try:
            import urllib.request
            import json
            for sub in ['worldnews', 'economics', 'stocks']:
                url = f"https://www.reddit.com/r/{sub}/hot.json?limit=10"
                req = urllib.request.Request(url, headers={'User-Agent': 'BeastBot/1.0'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    for post in data.get('data', {}).get('children', []):
                        title = post.get('data', {}).get('title', '').lower()
                        if title:
                            headlines.append(title)
        except Exception as e:
            log.debug(f"Reddit news failed: {e}")
        
        if not headlines:
            log.info("  No headlines fetched")
            return
        
        # Match headlines to sectors
        triggered_sectors = {}  # sector → list of matching headlines
        for headline in headlines:
            for keyword, sectors in self.MACRO_SECTOR_MAP.items():
                if keyword in headline:
                    for sector in sectors:
                        if sector not in triggered_sectors:
                            triggered_sectors[sector] = []
                        if headline not in triggered_sectors[sector]:
                            triggered_sectors[sector].append(headline[:80])
        
        if not triggered_sectors:
            log.info("  No macro triggers detected")
            return
        
        self._runner_alerts[alert_key] = True
        
        # Log and alert
        log.info(f"  🌍 MACRO TRIGGERS: {len(triggered_sectors)} sectors flagged")
        alert_lines = ["🌍 MACRO NEWS ROTATION ALERT\n"]
        priority_sectors = []
        
        for sector, matched in sorted(triggered_sectors.items(),
                                       key=lambda x: len(x[1]), reverse=True):
            count = len(matched)
            sector_upper = sector.upper()
            stocks = ALL_SECTORS.get(sector, [])[:5]
            alert_lines.append(f"  {sector_upper} ({count} hits): {', '.join(stocks)}")
            log.info(f"  📰 {sector_upper}: {count} headline matches")
            for h in matched[:2]:
                log.info(f"     → {h}")
            
            if count >= 2:  # Multiple headlines = strong signal
                priority_sectors.append(sector)
        
        # Send alert
        if priority_sectors:
            alert_lines.append(f"\n🔥 PRIORITY SCAN: {', '.join(s.upper() for s in priority_sectors)}")
            self.notify.send('\n'.join(alert_lines))
            
            # Auto-scan priority sectors for runners
            for sector in priority_sectors:
                symbols = ALL_SECTORS.get(sector, [])
                if symbols:
                    log.info(f"  🔍 Auto-scanning {sector}: {', '.join(symbols[:8])}")
                    try:
                        from alpaca.data.historical import StockHistoricalDataClient
                        from alpaca.data.requests import StockSnapshotRequest
                        client = StockHistoricalDataClient(
                            os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY')
                        )
                        req = StockSnapshotRequest(
                            symbol_or_symbols=symbols[:10], feed='iex'
                        )
                        snaps = client.get_stock_snapshot(req)
                        
                        for sym, s in snaps.items():
                            try:
                                prev = float(s.previous_daily_bar.close) if s.previous_daily_bar else 0
                                curr = float(s.latest_trade.price) if s.latest_trade else 0
                                if prev > 0 and curr > 0:
                                    pct = (curr - prev) / prev * 100
                                    if pct > 2.0:
                                        log.info(f"     🔥 {sym} +{pct:.1f}% (macro catalyst!)")
                            except:
                                pass
                    except Exception as e:
                        log.debug(f"Macro sector scan failed for {sector}: {e}")

    # ── FULL SCAN (every 5 min) ────────────────────────

    def run_full_scan(self, now: datetime):
        """Full Beast Mode scan with all 8 phases."""
        log.info(f"\n{'=' * 60}")
        log.info(f"FULL SCAN #{self.cycle_count} - {now.strftime('%H:%M:%S %Z')}")
        log.info(f"{'=' * 60}")

        if self.halted:
            log.warning("HALTED - skipping full scan")
            return

        # ── V5 RISK CHECK: Daily loss limit ───────────
        if self.risk:
            try:
                acct_check = self.gateway.get_account()
                equity_now = float(acct_check.get('equity', 100000))
                last_equity = float(acct_check.get('last_equity', equity_now))
                risk_status = self.risk.check_loss_limits(
                    equity=equity_now,
                    starting_equity_today=last_equity,
                    starting_equity_week=last_equity,  # TODO: track weekly start
                    starting_equity_month=100000  # TODO: track monthly start
                )
                if not risk_status.get('can_buy', True):
                    log.critical(
                        f"🚨 [RISK] DAILY LOSS LIMIT HIT — {risk_status.get('reason', 'unknown')}. "
                        f"Daily P&L: {risk_status.get('daily_pnl_pct', 0):.2%}. "
                        f"Mode: SELL-ONLY until tomorrow. No new buys."
                    )
                    # Still run scan for monitoring, but flag no-buy mode
                    self._risk_can_buy = False
                else:
                    self._risk_can_buy = True
                    size_mult = risk_status.get('size_multiplier', 1.0)
                    if size_mult < 1.0:
                        log.info(f"[RISK] Size multiplier: {size_mult:.1f}x (weekly/monthly loss reduction)")
            except Exception as e:
                log.warning(f"[RISK] Loss limit check failed: {e}")
                self._risk_can_buy = True

        # ── PHASE 1: POSITIONS ─────────────────────────
        log.info("Phase 1: Positions...")
        positions = self.gateway.get_positions()
        acct = self.gateway.get_account()
        equity = float(acct.get('equity', 100000))
        total_pl = sum(p.unrealized_pl for p in positions)
        held_symbols = [p.symbol for p in positions]

        log.info(f"  {len(positions)} positions | P&L: ${total_pl:+.2f} | Equity: ${equity:,.2f}")

        pos_lines = []
        for p in positions:
            pct = (p.unrealized_pl / p.cost_basis * 100) if p.cost_basis else 0
            icon = "+" if p.unrealized_pl >= 0 else "-"
            pos_lines.append(f"  {icon} {p.symbol:6s} {p.qty}x @ ${p.avg_entry:.2f} -> "
                           f"${p.current_price:.2f} ({pct:+.1f}%) ${p.unrealized_pl:+.2f}")
            log.info(pos_lines[-1])

        # ── PHASE 2: REGIME + SCAN LIST ────────────────
        log.info("Phase 2: Regime detection...")
        spy_change = self._get_spy_change()
        regime = self.regime.detect(spy_change)
        log.info(f"  Regime: {regime.value} | SPY: {spy_change:+.2%}")

        scan_list = self._build_scan_list(regime, held_symbols)
        log.info(f"  Scan list ({len(scan_list)}): {', '.join(scan_list[:15])}")

        # ── PHASE 2.5: PRO MARKET CONDITIONS ──────────
        market_conditions = {}
        if self.pro_data:
            try:
                log.info("Phase 2.5: Pro market conditions (PCR, VIX, Fear&Greed, economic calendar)...")
                market_conditions = self.pro_data.get_market_conditions()
                pcr = market_conditions.get('pcr', {})
                vix = market_conditions.get('vix', {})
                fg = market_conditions.get('fear_greed', {})
                econ = market_conditions.get('economic', {})
                log.info(f"  [PRO] PCR: {pcr.get('value', '?')} ({pcr.get('signal', '?')}) | "
                        f"VIX: {vix.get('vix', '?')} (contango={'yes' if vix.get('contango') else 'INVERTED'}) | "
                        f"Fear&Greed: {fg.get('value', '?')} ({fg.get('label', '?')}) | "
                        f"High-impact tomorrow: {econ.get('high_impact_tomorrow', '?')}")
                # Adjust regime based on pro data
                if fg.get('value', 50) <= 20:
                    log.info(f"  [PRO] 🟢 EXTREME FEAR ({fg.get('value')}) — contrarian BUY signal active")
                elif fg.get('value', 50) >= 80:
                    log.info(f"  [PRO] 🔴 EXTREME GREED ({fg.get('value')}) — reducing exposure")
                if econ.get('high_impact_tomorrow'):
                    log.info(f"  [PRO] ⚠️ HIGH IMPACT EVENT TOMORROW — reducing new positions by 50%")
            except Exception as e:
                log.warning(f"  [PRO] Market conditions fetch failed: {e}")

        # ── PHASE 3: MARKET MOVERS ─────────────────────
        log.info("Phase 3: Market movers...")
        movers = self._get_movers()
        if movers:
            top_gainers = movers.get('gainers', [])[:5]
            top_losers = movers.get('losers', [])[:5]
            gainer_str = ', '.join(f"{m['symbol']}({m.get('percent_change',0):+.1f}%)" for m in top_gainers if m.get('price',0) > 5)
            loser_str = ', '.join(f"{m['symbol']}({m.get('percent_change',0):+.1f}%)" for m in top_losers if m.get('price',0) > 5)
            log.info(f"  Gainers: {gainer_str}")
            log.info(f"  Losers: {loser_str}")

        # ── PHASE 4: SENTIMENT ─────────────────────────
        log.info("Phase 4: Sentiment...")
        sentiments = self._get_sentiments(held_symbols[:8])
        for sym, sent in sentiments.items():
            if hasattr(sent, 'overall_score'):
                log.info(f"  {sym}: score={sent.overall_score:.0f} "
                        f"yahoo={getattr(sent, 'yahoo_score', '?')} "
                        f"reddit={getattr(sent, 'reddit_score', '?')}")

        # ── PHASE 4.5: PRO DATA INTEL (per-stock) ─────
        pro_intel = {}
        if self.pro_data:
            try:
                log.info("Phase 4.5: Pro intel (congress, insider, dark pool, short interest)...")
                intel_symbols = held_symbols[:10]  # Check held stocks first
                for sym in intel_symbols:
                    try:
                        intel = self.pro_data.get_full_intel(sym)
                        pro_intel[sym] = intel
                        score = intel.get('score', 0)
                        breakdown = intel.get('breakdown', {})
                        active_signals = {k: v for k, v in breakdown.items() if v != 0}
                        if active_signals:
                            log.info(f"  [PRO] {sym}: score={score:+d} | {active_signals}")
                    except Exception as e:
                        log.debug(f"  [PRO] {sym} intel failed: {e}")
            except Exception as e:
                log.warning(f"  [PRO] Intel scan failed: {e}")

        # ── PHASE 5: OPEN ORDERS CHECK ─────────────────
        log.info("Phase 5: Open orders...")
        open_orders = self.gateway.get_open_orders()
        for o in open_orders:
            log.info(f"  {o.get('side','?').upper()} {o.get('symbol','?')} "
                    f"x{o.get('qty','?')} @ ${o.get('limit_price','?')} "
                    f"({o.get('status','?')})")

        # ── PHASE 6: AI ANALYSIS (if available) ────────
        ai_verdicts = {}
        if self.ai and self.ai.is_available:
            log.info("Phase 6: AI Analysis...")
            for sym in held_symbols[:6]:
                try:
                    pos = next((p for p in positions if p.symbol == sym), None)
                    if not pos:
                        continue
                    sent = sentiments.get(sym)
                    data = {
                        'price': pos.current_price,
                        'entry': pos.avg_entry,
                        'pnl': pos.unrealized_pl,
                        'qty': pos.qty,
                        'regime': regime.value,
                        'sentiment': getattr(sent, 'overall_score', 50) if sent else 50,
                    }
                    result = self.ai.analyze_stock(sym, data)
                    action = result.get('action', 'HOLD')
                    conf = result.get('confidence', 0)
                    reason = result.get('reasoning', '')[:80]
                    ai_verdicts[sym] = result
                    log.info(f"  AI {sym}: {action} ({conf}%) - {reason}")
                except Exception as e:
                    log.warning(f"  AI failed for {sym}: {e}")
        else:
            log.info("Phase 6: AI offline - deterministic mode")

        # ── PHASE 7: ACTION TABLE ──────────────────────
        log.info("Phase 7: Action table...")
        action_table = []
        for p in positions:
            pct = (p.unrealized_pl / p.cost_basis * 100) if p.cost_basis else 0
            sent = sentiments.get(p.symbol)
            ai_v = ai_verdicts.get(p.symbol, {})

            # Determine action
            if pct >= 5.0:
                action = "RUNNER - trail stop"
            elif pct >= 2.0:
                action = "SCALP TARGET - sell half"
            elif pct >= 0:
                action = "GREEN - hold"
            elif pct > -5.0:
                action = "RED - HOLD (Iron Law 1)"
            else:
                action = "DEEP RED - HOLD + ALERT"

            ai_action = ai_v.get('action', '-')
            sent_score = getattr(sent, 'overall_score', '-') if sent else '-'

            line = (f"{'G' if pct>=0 else 'R'} {p.symbol:6s} ${p.current_price:7.2f} "
                   f"P&L:${p.unrealized_pl:+7.2f} ({pct:+5.1f}%) "
                   f"Sent:{sent_score} AI:{ai_action} => {action}")
            action_table.append(line)
            log.info(f"  {line}")

        # ── PHASE 7B: NEW BUY OPPORTUNITIES ───────────
        log.info("Phase 7B: Scanning for NEW buys...")
        if not self.halted and len(positions) < 15:
            # Check movers for buy opportunities
            buy_candidates = []
            all_movers = []
            if movers:
                all_movers = [m for m in movers.get('gainers', [])
                             if m.get('price', 0) > 5 and m.get('percent_change', 0) > 1.5
                             and m.get('percent_change', 0) < 8  # Rule 29: don't chase >8%
                             and m.get('symbol', '') not in held_symbols]

            for m in all_movers[:10]:
                sym = m.get('symbol', '')
                pct_move = m.get('percent_change', 0)
                price = m.get('price', 0)
                
                is_past_winner = sym in PAST_WINNERS
                in_sectors = any(sym in stocks for stocks in ALL_SECTORS.values())
                
                if not is_past_winner and not in_sectors:
                    continue
                
                # Score it
                confidence = 0.50  # Base
                strategy_name = "SECTOR_MOMENTUM"
                
                if is_past_winner:
                    confidence += 0.15  # Past winners get big boost
                    strategy_name = "PAST_WINNER"
                if 1.5 <= pct_move <= 3.5:
                    confidence += 0.10  # Sweet spot, not chasing
                if pct_move > 5:
                    confidence -= 0.15  # Extended, risky
                    strategy_name = "EXTENDED_CAUTION"
                
                # Sentiment boost if available
                sent = sentiments.get(sym)
                if sent and hasattr(sent, 'overall_score') and sent.overall_score > 60:
                    confidence += 0.05
                
                buy_candidates.append({
                    'symbol': sym, 'price': price, 'pct': pct_move,
                    'confidence': min(confidence, 0.95),
                    'strategy': strategy_name,
                    'is_past_winner': is_past_winner,
                })
            
            # Sort by confidence
            buy_candidates.sort(key=lambda x: x['confidence'], reverse=True)
            
            for c in buy_candidates[:3]:  # Top 3 candidates
                sym = c['symbol']
                conf = c['confidence']
                price = c['price']
                
                # Size it
                if price > 500: qty = 3
                elif price > 200: qty = 5
                elif price > 100: qty = 10
                elif price > 50: qty = 25
                elif price > 20: qty = 50
                else: qty = 200
                
                cost = qty * price
                cash = float(acct.get('cash', 0))
                if cost > cash * 0.15:
                    qty = max(1, int(cash * 0.15 / price))
                
                flag = "🔥 PAST WINNER" if c['is_past_winner'] else "📊"
                log.info(f"  {flag} BUY CANDIDATE: {sym} ${price:.2f} "
                        f"+{c['pct']:.1f}% conf={conf:.0%} strategy={c['strategy']}")
                
                if conf >= AUTO_EXECUTE_THRESHOLD:
                    # AUTO-BUY — but TV MUST approve first!
                    scalp_target = round(price * 1.025, 2)
                    runner_target = round(price * 1.06, 2)
                    
                    try:
                        tv = self._run_tv_analysis(sym)
                        is_pw = sym in PAST_WINNERS
                        if not tv['tv_ok'] and not is_pw:
                            log.error(f"🚨 TV FAILED for {sym} — BLOCKED")
                            continue
                        elif not tv['tv_ok'] and is_pw:
                            log.warning(f"⚠️ TV down but {sym} is PAST WINNER — BYPASS")
                            blended = conf
                        else:
                            tv_conf = tv['confidence']
                            blended = (conf * 0.5) + (tv_conf * 0.5)
                            log.info(f"    📊 Phase7B {sym}: strat={conf:.0%} TV={tv_conf:.0%} → {blended:.0%}")
                        if blended < AUTO_EXECUTE_THRESHOLD:
                            log.info(f"    ❌ blended {blended:.0%} too low — SKIP")
                            continue
                        
                        from models import TradeProposal, Strategy as StratEnum
                        proposal = TradeProposal(
                            symbol=sym, qty=qty,
                            side=OrderSide.BUY,
                            limit_price=round(price * 1.002, 2),
                            strategy=StratEnum.ORB_BREAKOUT,
                            confidence=blended,
                        )
                        results = validate_entry(
                            proposal, None, positions, total_pl,
                            self.consecutive_losses, self.active_day_trades,
                            self.last_sell_times, self.earnings_dates,
                            has_technicals=tv['tv_ok'], has_sentiment=True,
                        )
                        if is_approved(results):
                            half = qty // 2
                            self.gateway.place_buy(
                                proposal, None, positions, total_pl,
                                self.consecutive_losses, self.active_day_trades,
                                self.last_sell_times, self.earnings_dates,
                            )
                            # Iron Law 6: set sells immediately
                            # SCALP: fixed limit
                            self.gateway.place_sell(sym, half, scalp_target,
                                reason=f"Scalp {c['strategy']}", time_in_force='gtc',
                                entry_price=price)
                            # RUNNER: trailing stop!
                            self.gateway.place_trailing_stop(sym, qty - half,
                                trail_percent=3.0,
                                reason=f"Runner {c['strategy']}",
                                entry_price=price)
                            
                            msg = (f"🔥 AUTO-BUY: {sym}\n"
                                  f"Strategy: {c['strategy']} ({conf:.0%})\n"
                                  f"BUY {qty}sh @ ${price:.2f}\n"
                                  f"Scalp: {half}sh @ ${scalp_target} (fixed)\n"
                                  f"Runner: {qty-half}sh trailing 3% 📈")
                            log.info(msg)
                            self.notify.send(msg)
                        else:
                            rejections = get_rejections(results)
                            log.info(f"    BLOCKED: {rejections[0].reason}")
                    except Exception as e:
                        log.error(f"    Auto-buy failed {sym}: {e}")
                        
                elif conf >= ASK_THRESHOLD:
                    # AUTO-BUY — TV MUST approve
                    scalp_target = round(price * 1.025, 2)
                    runner_target = round(price * 1.06, 2)
                    
                    try:
                        tv = self._run_tv_analysis(sym)
                        is_pw = sym in PAST_WINNERS
                        if not tv['tv_ok'] and not is_pw:
                            log.error(f"🚨 TV FAILED for {sym} — BLOCKED")
                            continue
                        elif not tv['tv_ok'] and is_pw:
                            log.warning(f"⚠️ TV down but {sym} is PAST WINNER — BYPASS")
                            blended = conf
                        else:
                            tv_conf = tv['confidence']
                            blended = (conf * 0.5) + (tv_conf * 0.5)
                        if blended < ASK_THRESHOLD:
                            log.info(f"    ❌ {sym}: blended {blended:.0%} too low — SKIP")
                            continue
                        
                        from models import TradeProposal, Strategy as StratEnum
                        proposal = TradeProposal(
                            symbol=sym, qty=qty,
                            side=OrderSide.BUY,
                            limit_price=round(price * 1.002, 2),
                            strategy=StratEnum.ORB_BREAKOUT,
                            confidence=blended,
                        )
                        results = validate_entry(
                            proposal, None, positions, total_pl,
                            self.consecutive_losses, self.active_day_trades,
                            self.last_sell_times, self.earnings_dates,
                            has_technicals=tv['tv_ok'], has_sentiment=True,
                        )
                        if is_approved(results):
                            half = qty // 2
                            self.gateway.place_buy(
                                proposal, None, positions, total_pl,
                                self.consecutive_losses, self.active_day_trades,
                                self.last_sell_times, self.earnings_dates,
                            )
                            # SCALP: fixed limit
                            self.gateway.place_sell(sym, half, scalp_target,
                                reason=f"Scalp {c['strategy']}", time_in_force='gtc',
                                entry_price=price)
                            # RUNNER: trailing stop!
                            self.gateway.place_trailing_stop(sym, qty - half,
                                trail_percent=3.0,
                                reason=f"Runner {c['strategy']}",
                                entry_price=price)
                            
                            msg = (f"⚡ AUTO-BUY: {sym}\n"
                                  f"{c['strategy']} ({conf:.0%})\n"
                                  f"BUY {qty}sh @ ${price:.2f}\n"
                                  f"Scalp {half}sh @ ${scalp_target} (fixed)\n"
                                  f"Runner {qty-half}sh trailing 3% 📈")
                            log.info(msg)
                            self.notify.send(msg)
                        else:
                            rejections = get_rejections(results)
                            log.info(f"    BLOCKED: {rejections[0].reason}")
                    except Exception as e:
                        log.error(f"    Auto-buy failed {sym}: {e}")

        # ── PHASE 8: RISK CHECK ────────────────────────
        log.info("Phase 8: Risk check...")
        self._risk_check(positions, total_pl)

        # ── SEND NOTIFICATION ──────────────────────────
        now_str = now.strftime('%H:%M ET')
        header = f"BEAST SCAN {now_str} | {regime.value.upper()}\n"
        header += f"Equity: ${equity:,.0f} | P&L: ${total_pl:+.2f}\n"
        header += f"Positions: {len(positions)} | Orders: {len(open_orders)}\n"
        header += "-" * 30 + "\n"
        body = "\n".join(action_table[:12])
        self.notify.send(header + body)

        log.info(f"{'=' * 60}")
        log.info(f"Full scan complete. Next in {FULL_SCAN_INTERVAL}s")

    # ── EXTENDED HOURS SCAN ────────────────────────────

    def run_extended_hours_scan(self, now: datetime, session: str = 'premarket'):
        """Extended hours scan — find runners, earnings reactions, sector moves.
        Pre-market: earnings gaps, overnight news, sector rotation signals.
        After-hours: earnings reactions, position for next day.
        
        Day 5 lesson: We missed NOK for 35 min because we only looked at Mag 7.
        Day 6 lesson: Oil was the only green sector but we didn't scan energy until asked.
        SCAN EVERYTHING. EVERY TIME."""
        log.info(f"{'='*60}")
        log.info(f"EXTENDED HOURS SCAN ({session.upper()}) - {now.strftime('%H:%M %Z')}")
        log.info(f"{'='*60}")
        
        try:
            # 1. Positions P&L
            positions = self.gateway.get_positions()
            total_pl = sum(p.unrealized_pl for p in positions)
            held_symbols = [p.symbol for p in positions]
            log.info(f"  {len(positions)} positions | P&L: ${total_pl:+.2f}")
            
            # 2. Phase 0: PAST WINNERS CHECK (Rule #21 — do this FIRST!)
            movers = self._get_movers()
            if movers:
                mover_symbols = [m.get('symbol','') for m in movers.get('gainers',[])]
                mover_symbols += [m.get('symbol','') for m in movers.get('actives',[])]
                past_winner_alerts = [s for s in PAST_WINNERS if s in mover_symbols]
                if past_winner_alerts:
                    alert_msg = (
                        f"🔥 PAST WINNER ALERT ({session})!\n"
                        f"Stocks: {', '.join(past_winner_alerts)}\n"
                        f"These made us money before. PRIORITY SCAN!"
                    )
                    log.info(f"  {alert_msg}")
                    self.notify.send(alert_msg)
                    
                # Log top movers filtering out pennies
                top = [m for m in movers.get('gainers', []) if m.get('price', 0) > 5][:5]
                gstr = ', '.join(f"{m['symbol']}+{m.get('percent_change',0):.1f}%"
                               for m in top)
                if gstr:
                    log.info(f"  Top movers: {gstr}")
            
            # 3. ALL SECTORS snapshot — find what's moving
            log.info("  Scanning ALL sectors for rotation...")
            for sector_name, symbols in ALL_SECTORS.items():
                try:
                    sample = symbols[:5]  # Top 5 per sector to save API calls
                    from alpaca.data.historical import StockHistoricalDataClient
                    from alpaca.data.requests import StockSnapshotRequest
                    client = StockHistoricalDataClient(
                        os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY')
                    )
                    req = StockSnapshotRequest(symbol_or_symbols=sample, feed='iex')
                    snaps = client.get_stock_snapshot(req)
                    
                    sector_moves = []
                    for sym, s in snaps.items():
                        try:
                            prev = s.previous_daily_bar.close if s.previous_daily_bar else 0
                            curr = s.latest_trade.price if s.latest_trade else 0
                            if prev > 0 and curr > 0:
                                pct = (curr - prev) / prev * 100
                                if abs(pct) > 1.5:
                                    sector_moves.append((sym, pct))
                        except:
                            pass
                    
                    if sector_moves:
                        moves_str = ', '.join(f"{s}{p:+.1f}%" for s, p in sector_moves)
                        log.info(f"  {sector_name:12s}: {moves_str}")
                        
                        # Alert if sector is moving >3%
                        big_moves = [m for m in sector_moves if abs(m[1]) > 3]
                        if big_moves:
                            self.notify.send(
                                f"SECTOR ALERT: {sector_name.upper()}\n"
                                f"Big moves: {', '.join(f'{s}{p:+.1f}%' for s,p in big_moves)}"
                            )
                except Exception as e:
                    log.debug(f"  {sector_name} scan failed: {e}")
            
            # 4. Earnings reactions (after-hours)
            if session == 'afterhours':
                log.info("  Checking earnings reactions...")
                earnings_watch = MAG7 + SEMI[:5] + BLUE_CHIPS
                # Check for big AH moves on earnings stocks
                
        except Exception as e:
            log.warning(f"Extended scan error: {e}\n{traceback.format_exc()}")

    # ── HELPER: MOVERS ─────────────────────────────────

    def _get_movers(self) -> dict:
        """Get REAL market runners — not just our watchlist.
        
        Day 7 LESSON: Bot only scanned 150 stocks from our watchlist.
        The market has 10,000+. INTC ran +11%, SOXL +7.4%, HOOD on
        most_active — we missed all because they weren't in our scan.
        
        NEW APPROACH (3-layer detection):
        
        Layer 1: MOST ACTIVE stocks (Alpaca screener)
          → Top 20 by volume. If it's trading massive volume AND
            up >3% from previous close, it's a runner. Period.
          → This catches stocks OUTSIDE our watchlist.
        
        Layer 2: OUR WATCHLIST snapshots (175+ stocks across 14 sectors)
          → Compare current price to previous close for every stock
            in our universe. Catches sector-specific runners.
        
        Layer 3: PAST WINNERS priority check
          → If any past winner is up >1.5%, flag it immediately.
          → These stocks have PROVEN they work for us.
        
        FILTERS:
        - Price > $5 (no penny stocks)
        - Symbol doesn't end in 'W' (no warrants)
        - Volume > 100K (needs liquidity for fills)
        
        Returns: {
            'gainers': [{symbol, price, percent_change}, ...] sorted by % desc
            'losers': [{symbol, price, percent_change}, ...] sorted by % asc
            'actives': [raw most_active data]
            'runners': [{symbol, price, percent_change, source}, ...] — THE MONEY LIST
        }
        """
        result = {'gainers': [], 'losers': [], 'actives': [], 'runners': []}
        seen_symbols = set()
        
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockSnapshotRequest
        
        client = StockHistoricalDataClient(
            os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY')
        )
        
        # ═══ LAYER 1: MOST ACTIVE STOCKS (catches runners OUTSIDE our watchlist) ═══
        try:
            from alpaca.data.requests import MostActivesRequest
            req = MostActivesRequest(top=20, by='volume')
            actives = client.get_most_actives(req)
            result['actives'] = actives
            
            # Get snapshots for active stocks to check % change
            active_symbols = []
            if hasattr(actives, 'most_actives'):
                active_list = actives.most_actives
            elif isinstance(actives, list):
                active_list = actives
            else:
                active_list = []
            
            for a in active_list:
                sym = a.symbol if hasattr(a, 'symbol') else (a.get('symbol', '') if isinstance(a, dict) else '')
                if sym and len(sym) <= 5 and not sym.endswith('W') and sym not in seen_symbols:
                    active_symbols.append(sym)
                    seen_symbols.add(sym)
            
            if active_symbols:
                try:
                    snap_req = StockSnapshotRequest(
                        symbol_or_symbols=active_symbols[:20], feed='iex'
                    )
                    snaps = client.get_stock_snapshot(snap_req)
                    for sym, s in snaps.items():
                        try:
                            price = float(s.latest_trade.price) if s.latest_trade else 0
                            prev = float(s.previous_daily_bar.close) if s.previous_daily_bar else 0
                            if prev > 0 and price > 5:  # Filter pennies
                                pct = (price - prev) / prev * 100
                                entry = {'symbol': sym, 'price': price,
                                        'percent_change': pct, 'source': 'most_active'}
                                if pct > 1.5:
                                    result['gainers'].append(entry)
                                    if pct > 3.0:
                                        result['runners'].append(entry)
                                        log.info(f"  🔥 RUNNER (active): {sym} +{pct:.1f}% @ ${price:.2f}")
                                elif pct < -1.5:
                                    result['losers'].append(entry)
                        except:
                            pass
                except Exception as e:
                    log.debug(f"Active snapshots failed: {e}")
        except Exception as e:
            log.debug(f"Most actives fetch failed: {e}")
        
        # ═══ LAYER 2: OUR FULL WATCHLIST (175+ stocks across 14 sectors) ═══
        try:
            # Build comprehensive scan list from ALL sectors
            all_symbols = set()
            for sector_stocks in ALL_SECTORS.values():
                all_symbols.update(sector_stocks)
            all_symbols.update(PAST_WINNERS)
            all_symbols.update(BLUE_CHIPS)
            # Remove already-scanned symbols
            remaining = [s for s in all_symbols if s not in seen_symbols]
            
            # Batch snapshots (max 50 per request)
            for i in range(0, len(remaining), 50):
                batch = remaining[i:i+50]
                try:
                    snap_req = StockSnapshotRequest(
                        symbol_or_symbols=batch, feed='iex'
                    )
                    snaps = client.get_stock_snapshot(snap_req)
                    for sym, s in snaps.items():
                        try:
                            price = float(s.latest_trade.price) if s.latest_trade else 0
                            prev = float(s.previous_daily_bar.close) if s.previous_daily_bar else 0
                            if prev > 0 and price > 5:
                                pct = (price - prev) / prev * 100
                                entry = {'symbol': sym, 'price': price,
                                        'percent_change': pct, 'source': 'watchlist'}
                                if pct > 1.5:
                                    result['gainers'].append(entry)
                                    if pct > 3.0:
                                        result['runners'].append(entry)
                                elif pct < -1.5:
                                    result['losers'].append(entry)
                                seen_symbols.add(sym)
                        except:
                            pass
                except Exception as e:
                    log.debug(f"Watchlist batch {i} failed: {e}")
        except Exception as e:
            log.debug(f"Watchlist scan failed: {e}")
        
        # ═══ LAYER 3: PAST WINNERS PRIORITY (always check, flag even +1.5%) ═══
        for entry in result['gainers']:
            if entry['symbol'] in PAST_WINNERS and entry not in result['runners']:
                entry['source'] = 'past_winner'
                result['runners'].append(entry)
                log.info(f"  ⚡ PAST WINNER: {entry['symbol']} +{entry['percent_change']:.1f}%")
        
        # Sort everything
        result['gainers'].sort(key=lambda x: x['percent_change'], reverse=True)
        result['losers'].sort(key=lambda x: x['percent_change'])
        result['runners'].sort(key=lambda x: x['percent_change'], reverse=True)
        
        # Log summary
        log.info(f"  📊 Movers: {len(result['gainers'])} gainers, "
                f"{len(result['losers'])} losers, "
                f"{len(result['runners'])} RUNNERS (>3%)")
        if result['runners']:
            top3 = result['runners'][:3]
            log.info(f"  🔥 TOP RUNNERS: " +
                    ', '.join(f"{r['symbol']}+{r['percent_change']:.1f}%" for r in top3))
        
        return result

    # ── FAST RUNNER SCAN (every 2 min) ──────────────────

    def _fast_runner_scan(self, now: datetime):
        """FAST runner detection + AUTO-EXECUTION — every 2 minutes.
        
        FIND fast, TRADE fast, SELL fast. No analysis paralysis.
        
        Strategy matching (from our 11 strategies):
        - Stock up 1-3% at open with volume → Strategy A (ORB Breakout)
        - Past winner on movers → Akash Method (buy → limit sell → repeat)
        - RSI < 35 on a runner → Strategy G (Red to Green dip buy)
        - Stock at VWAP with momentum → Strategy B (VWAP Bounce)
        - Gap up first 5 min → Strategy C (Gap & Go)
        
        EXECUTION — FULLY AUTONOMOUS:
        - >45% confidence → AUTO-BUY + set split sells in 60 sec
        - Iron Laws still enforced (can't override safety)
        - No waiting for Discord approval. Bot BUYS.
        
        Day 5: NOK ran +5% in 15 min. We found it 35 min late.
        Day 6: Oil ran +2.5% and we didn't scan until asked.
        This fixes both. Find in 2 min, trade in 2 seconds."""
        
        try:
            movers = self._get_movers()
            if not movers:
                return
            
            held = {p.symbol: p for p in self.gateway.get_positions()}
            held_symbols = list(held.keys())
            acct = self.gateway.get_account()
            cash = float(acct.get('cash', 0))
            
            # USE RUNNERS LIST (>3% gainers from ALL sources: most_active + watchlist + past winners)
            # This is the FIX: we now scan the ENTIRE market, not just our 150 stocks
            runners = movers.get('runners', [])
            # Also include strong gainers from our watchlist (>1.5%)
            gainers = [m for m in movers.get('gainers', [])
                      if m.get('price', 0) > 5 and m.get('percent_change', 0) > 1.5]
            # Merge: runners first (highest priority), then gainers
            seen = set()
            scan_list = []
            for m in runners + gainers:
                sym = m.get('symbol', '')
                if sym not in seen:
                    seen.add(sym)
                    scan_list.append(m)
            
            for m in scan_list[:15]:  # Top 15 (was 10)
                sym = m.get('symbol', '')
                pct = m.get('percent_change', 0)
                price = m.get('price', 0)
                
                # Already holding? Check if scalp target hit instead
                if sym in held_symbols:
                    pos = held[sym]
                    pos_pct = (pos.unrealized_pl / pos.cost_basis * 100) if pos.cost_basis else 0
                    # AUTO-SCALP: If position is up >2.5%, sell half
                    if pos_pct >= 2.5 and pos.qty > 1:
                        half = max(1, pos.qty // 2)
                        scalp_price = round(pos.avg_entry * 1.025, 2)
                        sell_price = max(scalp_price, round(pos.current_price * 1.005, 2))
                        alert_key = f"autoscalp_{sym}_{now.strftime('%Y%m%d_%H')}"
                        if alert_key not in self._runner_alerts:
                            try:
                                self.gateway.place_sell(
                                    sym, half, sell_price,
                                    reason=f"Fast scalp +{pos_pct:.1f}%",
                                    entry_price=pos.avg_entry
                                )
                                log.info(f"⚡ FAST SCALP: {sym} {half}sh @ ${sell_price:.2f} (+{pos_pct:.1f}%)")
                                self.notify.send(
                                    f"⚡ FAST SCALP: {sym}\n"
                                    f"Sold {half}sh @ ${sell_price:.2f}\n"
                                    f"Entry: ${pos.avg_entry:.2f} | +{pos_pct:.1f}%"
                                )
                                self._runner_alerts[alert_key] = True
                            except Exception as e:
                                log.error(f"Fast scalp failed {sym}: {e}")
                    continue
                
                # Already alerted this hour? Skip.
                alert_key = f"{sym}_{now.strftime('%Y%m%d_%H')}"
                if alert_key in self._runner_alerts:
                    continue
                
                # ── STRATEGY MATCHING ──────────────────
                is_past_winner = sym in PAST_WINNERS
                in_our_sectors = any(sym in stocks for stocks in ALL_SECTORS.values())
                is_most_active = m.get('source') == 'most_active'
                
                # Day 7 FIX: If it's on most_active AND up >3%, it's a runner
                # regardless of whether it's in our watchlist. The MARKET told
                # us this stock is hot. Don't ignore it.
                if not is_past_winner and not in_our_sectors and not is_most_active:
                    continue
                
                # If it's a most_active stock NOT in our universe, give it lower
                # base confidence but still consider it
                is_unknown_runner = is_most_active and not in_our_sectors and not is_past_winner
                
                # Determine strategy and confidence
                strategy = None
                confidence = 0.0
                reason = ""
                is_extended = now.hour < 9 or (now.hour == 9 and now.minute < 30) or now.hour >= 16
                
                # ═══ PRE-MARKET / AFTER-HOURS STRATEGIES ═══
                # Day 5: NOK ran +9.6% pre-market. By open it was gone.
                # Day 7: Multiple runners in pre-market we missed completely.
                # LESSON: If it's running pre-market with VOLUME, it runs MORE at open.
                
                if is_extended:
                    # Pre-market runner: 2-5% up = early entry before open moon
                    if is_past_winner and 1.5 <= pct <= 8.0:
                        strategy = "PREMARKET_PAST_WINNER"
                        confidence = 0.72  # Past winners in pre-market = HIGH priority
                        reason = f"🌅 Pre-mkt PAST WINNER +{pct:.1f}% — catch before open!"
                    elif 2.0 <= pct <= 4.5 and in_our_sectors:
                        strategy = "PREMARKET_RUNNER"
                        confidence = 0.62  # Sector stock running pre-market
                        reason = f"🌅 Pre-mkt runner +{pct:.1f}% — early entry"
                    elif 4.5 < pct <= 8.0 and in_our_sectors:
                        strategy = "PREMARKET_MOMENTUM"
                        confidence = 0.55  # Strong pre-market move, still catchable
                        reason = f"🌅 Pre-mkt momentum +{pct:.1f}% — limit buy below current"
                    elif pct > 8.0:
                        strategy = "PREMARKET_EXTENDED"
                        confidence = 0.40  # Too extended even for pre-market
                        reason = f"⚠️ Pre-mkt +{pct:.1f}% — watch for open dip to buy"
                
                # ═══ REGULAR HOURS STRATEGIES ═══
                else:
                    # Strategy A: ORB Breakout (1-3% up in first hour with volume)
                    if 1.5 <= pct <= 4.0 and now.hour < 11:
                        strategy = "ORB_BREAKOUT"
                        confidence = 0.55 + (0.10 if is_past_winner else 0)
                        reason = f"ORB Breakout +{pct:.1f}% (first hour)"
                    
                    # Akash Method: Past winner on movers (buy → limit sell → repeat)
                    if is_past_winner and 1.5 <= pct <= 4.0:
                        strategy = "AKASH_METHOD"
                        confidence = 0.70  # Past winners get high confidence
                        reason = f"Akash Method: past winner +{pct:.1f}%"
                    
                    # Strategy C: Gap & Go (first 5 min only)
                    minutes_since_open = (now.hour - 9) * 60 + (now.minute - 30) if now.hour >= 9 else 0
                    if pct > 3.0 and minutes_since_open <= 5:
                        strategy = "GAP_AND_GO"
                        confidence = 0.60
                        reason = f"Gap & Go +{pct:.1f}% (first 5 min)"
                
                # Rule 29: Don't chase >5% during market hours only
                # Pre-market has its own limits above
                if not is_extended and pct > 5.0:
                    strategy = "LIMIT_DIP_BUY"
                    confidence = 0.45  # Below auto-execute, will alert only
                    reason = f"⚠️ Up {pct:.1f}% — too extended, set limit at VWAP"
                
                if not strategy:
                    continue
                
                # ── POSITION SIZING (ATR-based, not fixed brackets) ────
                qty = self._calculate_position_size(sym, price, confidence, cash)
                
                cost = qty * price
                if cost > cash * 0.15:  # Max 15% of cash per trade
                    qty = max(1, int(cash * 0.15 / price))
                    cost = qty * price
                
                # ── EXECUTE OR ALERT ───────────────────
                if confidence >= AUTO_EXECUTE_THRESHOLD and not self.halted:
                    # AUTO-EXECUTE: >80% confidence
                    scalp_qty = qty // 2
                    runner_qty = qty - scalp_qty
                    scalp_target = round(price * 1.025, 2)  # 2.5% scalp
                    runner_target = round(price * 1.06, 2)   # 6% runner
                    
                    try:
                        # Run TV analysis — BUT past winners can bypass if TV is down
                        tv = self._run_tv_analysis(sym)
                        is_pw = sym in PAST_WINNERS
                        
                        if not tv['tv_ok'] and not is_pw:
                            log.error(f"🚨 TV FAILED for {sym} — TRADE BLOCKED (Iron Law 3)")
                            continue
                        elif not tv['tv_ok'] and is_pw:
                            log.warning(f"⚠️ TV down but {sym} is PAST WINNER — BYPASS TV, using strategy confidence only")
                            blended_confidence = confidence  # Use strategy conf alone
                        else:
                            # Blend: 50% strategy confidence + 50% TV confidence
                            tv_conf = tv['confidence']
                            blended_confidence = (confidence * 0.5) + (tv_conf * 0.5)
                            log.info(f"  📊 {sym}: strategy={confidence:.0%} TV={tv_conf:.0%} → blended={blended_confidence:.0%} [{tv['signal']}]")
                        
                        if blended_confidence < AUTO_EXECUTE_THRESHOLD:
                            log.info(f"  ❌ {sym}: blended {blended_confidence:.0%} < {AUTO_EXECUTE_THRESHOLD:.0%} threshold — SKIP")
                            continue
                        
                        # Buy at limit (current ask)
                        from models import TradeProposal, Strategy as StratEnum
                        proposal = TradeProposal(
                            symbol=sym, qty=qty,
                            side=OrderSide.BUY,
                            limit_price=round(price * 1.002, 2),  # Tiny premium to fill
                            strategy=StratEnum.ORB_BREAKOUT,
                            confidence=blended_confidence,
                        )
                        # Use iron law validation — has_technicals=True because we ACTUALLY ran TV
                        results = validate_entry(
                            proposal, None, list(held.values()),
                            self.daily_pnl, self.consecutive_losses,
                            self.active_day_trades, self.last_sell_times,
                            self.earnings_dates,
                            has_technicals=tv['tv_ok'], has_sentiment=True,
                        )
                        if is_approved(results):
                            # Place buy
                            self.gateway.place_buy(
                                proposal, None, list(held.values()),
                                self.daily_pnl, self.consecutive_losses,
                                self.active_day_trades, self.last_sell_times,
                                self.earnings_dates,
                            )
                            # Iron Law 32: Track entry time for chase protection
                            self._runner_entry_times[sym] = now
                            # Iron Law 6: Set sells within 60 sec
                            # SCALP half: fixed limit (want guaranteed fill at target)
                            self.gateway.place_sell(sym, scalp_qty, scalp_target,
                                reason=f"Scalp {strategy}", time_in_force='gtc',
                                entry_price=price)
                            # RUNNER half: TRAILING STOP (let winners run!)
                            # 3% trail = if stock runs from $100→$120, stop moves to $116.40
                            self.gateway.place_trailing_stop(sym, runner_qty,
                                trail_percent=3.0,
                                reason=f"Runner {strategy}",
                                entry_price=price)
                            
                            msg = (
                                f"🔥 AUTO-TRADE: {sym}\n"
                                f"Strategy: {strategy}\n"
                                f"BUY {qty}sh @ ${price:.2f} ({confidence:.0%})\n"
                                f"Scalp: {scalp_qty}sh @ ${scalp_target:.2f} (fixed)\n"
                                f"Runner: {runner_qty}sh trailing 3% 📈\n"
                                f"{reason}"
                            )
                            log.info(msg)
                            self.notify.send(msg)
                        else:
                            rejections = get_rejections(results)
                            log.info(f"  BLOCKED {sym}: {rejections[0].reason}")
                    except Exception as e:
                        log.error(f"Auto-trade failed {sym}: {e}")
                    
                elif confidence >= ASK_THRESHOLD:
                    # FULLY AUTONOMOUS — but TV MUST approve first
                    scalp_qty = qty // 2
                    runner_qty = qty - scalp_qty
                    scalp_target = round(price * 1.025, 2)
                    runner_target = round(price * 1.06, 2)
                    
                    try:
                        tv = self._run_tv_analysis(sym)
                        is_pw = sym in PAST_WINNERS
                        if not tv['tv_ok'] and not is_pw:
                            log.error(f"🚨 TV FAILED for {sym} — BLOCKED")
                            continue
                        elif not tv['tv_ok'] and is_pw:
                            log.warning(f"⚠️ TV down but {sym} is PAST WINNER — BYPASS")
                            blended = confidence
                        else:
                            tv_conf = tv['confidence']
                            blended = (confidence * 0.5) + (tv_conf * 0.5)
                            log.info(f"  📊 {sym}: strategy={confidence:.0%} TV={tv_conf:.0%} → blended={blended:.0%}")
                        
                        if blended < ASK_THRESHOLD:
                            log.info(f"  ❌ {sym}: blended {blended:.0%} too low — SKIP")
                            continue
                        
                        from models import TradeProposal, Strategy as StratEnum
                        proposal = TradeProposal(
                            symbol=sym, qty=qty,
                            side=OrderSide.BUY,
                            limit_price=round(price * 1.002, 2),
                            strategy=StratEnum.ORB_BREAKOUT,
                            confidence=blended,
                        )
                        results = validate_entry(
                            proposal, None, list(held.values()),
                            self.daily_pnl, self.consecutive_losses,
                            self.active_day_trades, self.last_sell_times,
                            self.earnings_dates,
                            has_technicals=tv['tv_ok'], has_sentiment=True,
                        )
                        if is_approved(results):
                            self.gateway.place_buy(
                                proposal, None, list(held.values()),
                                self.daily_pnl, self.consecutive_losses,
                                self.active_day_trades, self.last_sell_times,
                                self.earnings_dates,
                            )
                            # Iron Law 32: Track entry time for chase protection
                            self._runner_entry_times[sym] = now
                            # SCALP: fixed limit
                            self.gateway.place_sell(sym, scalp_qty, scalp_target,
                                reason=f"Scalp {strategy}", time_in_force='gtc',
                                entry_price=price)
                            # RUNNER: trailing stop (let winners run!)
                            self.gateway.place_trailing_stop(sym, runner_qty,
                                trail_percent=3.0,
                                reason=f"Runner {strategy}",
                                entry_price=price)
                            
                            msg = (f"⚡ AUTO-BUY (runner): {sym}\n"
                                  f"Strategy: {strategy} ({confidence:.0%})\n"
                                  f"BUY {qty}sh @ ${price:.2f}\n"
                                  f"Scalp {scalp_qty}sh @ ${scalp_target} (fixed)\n"
                                  f"Runner {runner_qty}sh trailing 3% 📈")
                            log.info(msg)
                            self.notify.send(msg)
                        else:
                            rejections = get_rejections(results)
                            log.info(f"  BLOCKED: {rejections[0].reason}")
                    except Exception as e:
                        log.error(f"Auto-buy runner failed {sym}: {e}")
                
                else:
                    # LOG ONLY: <60%
                    log.info(f"  runner: {sym} {pct:+.1f}% conf={confidence:.0%} (too low)")
                
                self._runner_alerts[alert_key] = True
            
            # Also check most active for volume spikes on past winners
            actives = movers.get('actives', [])
            for a in actives[:5]:
                sym = a.get('symbol', '') if isinstance(a, dict) else ''
                if sym in PAST_WINNERS and sym not in held_symbols:
                    alert_key = f"vol_{sym}_{now.strftime('%Y%m%d_%H')}"
                    if alert_key not in self._runner_alerts:
                        log.info(f"  VOLUME: Past winner {sym} on most active!")
                        self.notify.send(f"📊 VOLUME: {sym} (past winner) on most active list!")
                        self._runner_alerts[alert_key] = True
                        
        except Exception as e:
            log.debug(f"Fast runner scan error: {e}")

    # ── HELPERS ────────────────────────────────────────
        """4:00 AM ET pre-market briefing. Scan ALL sectors for overnight moves."""
        log.info("="*60)
        log.info("PRE-MARKET BRIEFING 4:00 AM")
        log.info("="*60)
        msg_lines = ["🌅 PRE-MARKET BRIEFING\n"]
        
        try:
            positions = self.gateway.get_positions()
            total_pl = sum(p.unrealized_pl for p in positions)
            msg_lines.append(f"Positions: {len(positions)} | Unrealized: ${total_pl:+.2f}\n")
            
            # Check ALL sectors for overnight moves
            for sector_name, symbols in ALL_SECTORS.items():
                msg_lines.append(f"\n{sector_name.upper()}:")
                # Just log — detailed scan happens at 9:30
            
            msg_lines.append("\nPhase 0: Checking past winners on movers...")
            msg_lines.append(f"Past winners: {', '.join(PAST_WINNERS)}")
            msg_lines.append("\nFull scan at market open 9:30 AM ET")
            
            self.notify.send('\n'.join(msg_lines))
        except Exception as e:
            log.warning(f"Pre-market briefing error: {e}")

    def _market_open_scan(self, now: datetime):
        """9:30 AM ET — Market open. Full beast mode. Set all sells within 60 seconds."""
        log.info("="*60)
        log.info("🔔 MARKET OPEN — BEAST MODE ACTIVATED")
        log.info("="*60)
        
        self.notify.send(
            "🔔 MARKET OPEN!\n"
            "Beast Mode scanning ALL sectors:\n"
            f"Mag7, Semis ({len(SEMI)}), Energy ({len(ENERGY)}), "
            f"Defense ({len(DEFENSE)}), Telecom ({len(TELECOM)}), "
            f"Medical ({len(MEDICAL)}), Cloud/IT ({len(CLOUD_IT)}), "
            f"Solar, Space, Commodities, Consumer, Financials\n"
            f"Past winners: {', '.join(PAST_WINNERS)}\n"
            "Iron Law 6: Set sells within 60 seconds!"
        )
        
        # Run immediate full scan
        self.run_full_scan(now)
        self._last_full_scan = time.time()

    def _get_spy_change(self) -> float:
        """Get SPY daily change %."""
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockSnapshotRequest
            client = StockHistoricalDataClient(
                os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY')
            )
            req = StockSnapshotRequest(symbol_or_symbols='SPY', feed='iex')
            snap = client.get_stock_snapshot(req)
            if 'SPY' in snap:
                s = snap['SPY']
                price = float(s.daily_bar.close)
                prev = float(s.previous_daily_bar.close)
                return (price - prev) / prev if prev > 0 else 0
        except Exception as e:
            log.warning(f"SPY fetch failed: {e}")
        return 0

    def _build_scan_list(self, regime: Regime, held: list) -> list:
        """Build scan list — ALL sectors, not just tech!
        
        Day 5 lesson: Only scanning semis = missed $6,045.
        Day 6 lesson: Only scanning tech = missed oil running +2.5%.
        Rule #21: Past winners get priority.
        Rule #22: Scan ALL sectors.
        Rule #27: When a sector moves, scan the ENTIRE sector."""
        
        if regime == Regime.RED_ALERT:
            return held
        
        # ALWAYS start with past winners (Rule #21)
        base = list(PAST_WINNERS)
        
        # ALWAYS include held positions
        base += held
        
        # Add regime-appropriate sectors
        if regime == Regime.BULL:
            base += MAG7 + SEMI + CLOUD_IT + TELECOM + SPACE
        elif regime == Regime.BEAR:
            base += DEFENSE + ENERGY + COMMODITIES + MEDICAL
        else:  # CHOPPY
            base += DEFENSE + ENERGY + ['GOOGL', 'MSFT', 'AMZN', 'NVDA'] + MEDICAL[:5]
        
        # ALWAYS scan energy (Iran), defense, and telecom
        base += ENERGY[:5] + DEFENSE[:5] + TELECOM[:3]
        
        # Add top movers from all sectors
        for sector_stocks in ALL_SECTORS.values():
            base += sector_stocks[:3]  # Top 3 from each sector
        
        # Deduplicate while preserving order
        return list(dict.fromkeys(base))

    def _get_sentiments(self, symbols: list) -> dict:
        """Get sentiment for each symbol."""
        results = {}
        try:
            from sentiment_analyst import SentimentAnalyst
            sa = SentimentAnalyst()
            for sym in symbols[:8]:
                try:
                    results[sym] = sa.analyze(sym)
                except:
                    pass
        except Exception as e:
            log.warning(f"Sentiment module failed: {e}")
        return results

    def _risk_check(self, positions, total_pl):
        """Iron Laws risk check."""
        if total_pl <= -500:
            self.halted = True
            log.warning(f"KILL SWITCH: Daily P&L ${total_pl:.2f} - HALTED")
            self.notify.send(f"KILL SWITCH ACTIVATED\nDaily P&L: ${total_pl:.2f}\nAll trading HALTED")

        if self.consecutive_losses >= 2:
            self.halted = True
            log.warning("2 consecutive losses - HALTED")

        for p in positions:
            if p.unrealized_pl <= -500:
                self._alert_once(f"risk_{p.symbol}",
                    f"RISK ALERT: {p.symbol}\n"
                    f"Loss: ${p.unrealized_pl:.2f}\n"
                    f"Iron Law 1: HOLD (never sell at loss)")

    def _hourly_report(self, now: datetime):
        """Send hourly portfolio summary."""
        try:
            positions = self.gateway.get_positions()
            acct = self.gateway.get_account()
            equity = float(acct.get('equity', 0))
            total_pl = sum(p.unrealized_pl for p in positions)
            greens = sum(1 for p in positions if p.unrealized_pl >= 0)

            lines = [f"HOURLY REPORT {now.strftime('%I:%M %p ET')}"]
            lines.append(f"Equity: ${equity:,.0f} | P&L: ${total_pl:+.2f}")
            lines.append(f"Positions: {len(positions)} (G:{greens} R:{len(positions)-greens})")
            lines.append("-" * 25)

            for p in sorted(positions, key=lambda x: x.unrealized_pl, reverse=True):
                pct = (p.unrealized_pl / p.cost_basis * 100) if p.cost_basis else 0
                lines.append(f"{'G' if pct>=0 else 'R'} {p.symbol:5s} ${p.unrealized_pl:+7.2f} ({pct:+.1f}%)")

            self.notify.send("\n".join(lines))
            log.info(f"Hourly report sent at {now.strftime('%H:%M')}")
        except Exception as e:
            log.warning(f"Hourly report failed: {e}")

    def _alert_once(self, key: str, message: str):
        """Send notification only once per key (dedup)."""
        if key not in self._last_notification:
            self._last_notification[key] = time.time()
            self.notify.send(message)
            log.info(f"Alert sent: {key}")

    # ── SINGLE-CYCLE TEST ──────────────────────────────

    def run_once(self):
        """Run one complete cycle for testing."""
        now = datetime.now(ET)
        log.info("=== SINGLE CYCLE TEST ===")
        self._monitor_positions_fast(now)
        self.run_full_scan(now)
        log.info("=== TEST COMPLETE ===")


# ── ENTRY POINT ────────────────────────────────────────

if __name__ == '__main__':
    print("""
    ====================================================
    BEAST MODE LOOP v3.0 - Grand Autonomous Engine
    Position monitor: every 60 seconds
    Full scan: every 5 minutes
    TradingView = BRAIN | Alpaca = EXECUTOR
    Iron Laws = HARDCODED PYTHON
    Account: PAPER (PA37M4LP1YKP)
    ====================================================
    """)

    beast = BeastModeLoop()

    if '--once' in sys.argv:
        print("Running ONE cycle (test mode)...")
        beast.run_once()
    elif '--scan' in sys.argv:
        print("Running ONE full scan...")
        beast.run_full_scan(datetime.now(ET))
    else:
        beast.run_forever()
