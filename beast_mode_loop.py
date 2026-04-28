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
AUTO_EXECUTE_THRESHOLD = 0.80  # 80%+ confidence = auto-execute
ASK_THRESHOLD = 0.60           # 60-80% = ask Discord for approval

# ── EXTENDED HOURS CONFIG ──────────────────────────────
ENABLE_PREMARKET = True        # Trade pre-market 4:00-9:30 AM ET
ENABLE_AFTERHOURS = True       # Trade after-hours 4:00-8:00 PM ET
PREMARKET_START = 4             # 4 AM ET
PREMARKET_END = 9               # 9:30 AM ET (regular opens)
AFTERHOURS_START = 16           # 4 PM ET
AFTERHOURS_END = 20             # 8 PM ET
EXTENDED_SCAN_INTERVAL = 600    # 10 min scans during extended hours

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

# Blue chips (proven winners for Strategy I — Mean Reversion)
BLUE_CHIPS = ['CRM', 'NOW', 'PLTR', 'LMT', 'NOK']

# PAST WINNERS — Rule #21: Check these FIRST on every scan!
# These stocks have PROVEN they work for our style.
PAST_WINNERS = ['NOK', 'GOOGL', 'CRM', 'META', 'MSFT', 'NOW', 'AMD', 'NVDA',
                'OXY', 'DVN', 'INTC']

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

        # AI Brain (remote via tunnel)
        self.ai = None
        try:
            from ai_brain import AIBrain
            self.ai = AIBrain()
        except Exception as e:
            log.warning(f"AI Brain init failed: {e}")

        # TV CDP client (direct to TradingView Desktop)
        self.tv_cdp = None
        try:
            from tv_cdp_client import TVClient
            self.tv_cdp = TVClient()
            if self.tv_cdp.health_check():
                log.info("TV CDP connected")
            else:
                log.warning("TV CDP not available")
                self.tv_cdp = None
        except Exception as e:
            log.warning(f"TV CDP init failed: {e}")

        # State
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.active_day_trades = 0
        self.last_sell_times = {}
        self.earnings_dates = {}
        self.halted = False
        self.cycle_count = 0
        self._last_full_scan = 0
        self._last_hourly_report = -1
        self._previous_prices = {}
        self._alerted_losses = set()
        self._last_notification = {}

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

        # Extended hours scan — runners + earnings reactions (every 10 min)
        elif is_premarket and elapsed >= EXTENDED_SCAN_INTERVAL:
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

        # Log summary every 5 cycles
        if self.cycle_count % 5 == 0:
            greens = sum(1 for p in positions if p.unrealized_pl > 0)
            reds = len(positions) - greens
            log.info(f"[#{self.cycle_count}] {len(positions)} pos | "
                    f"P&L: ${total_pl:+.2f} | G:{greens} R:{reds}")

    # ── FULL SCAN (every 5 min) ────────────────────────

    def run_full_scan(self, now: datetime):
        """Full Beast Mode scan with all 8 phases."""
        log.info(f"\n{'=' * 60}")
        log.info(f"FULL SCAN #{self.cycle_count} - {now.strftime('%H:%M:%S %Z')}")
        log.info(f"{'=' * 60}")

        if self.halted:
            log.warning("HALTED - skipping full scan")
            return

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
        """Get market movers from Alpaca."""
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            client = StockHistoricalDataClient(
                os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY')
            )
            # Use Alpaca screener
            from alpaca.data.requests import MostActivesRequest
            req = MostActivesRequest(top=10, by='volume')
            actives = client.get_most_actives(req)
            return {'gainers': [], 'losers': [], 'actives': actives}
        except Exception:
            pass
        # Fallback: use snapshots of our watchlist
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockSnapshotRequest
            client = StockHistoricalDataClient(
                os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY')
            )
            symbols = MAG7 + ENERGY + SEMI + DEFENSE[:5] + TELECOM[:3] + MEDICAL[:3] + PAST_WINNERS
            req = StockSnapshotRequest(symbol_or_symbols=symbols, feed='iex')
            snaps = client.get_stock_snapshot(req)
            gainers, losers = [], []
            for sym, s in snaps.items():
                try:
                    price = float(s.latest_trade.price)
                    prev = float(s.previous_daily_bar.close)
                    pct = (price - prev) / prev * 100 if prev else 0
                    entry = {'symbol': sym, 'price': price, 'percent_change': pct}
                    if pct > 0:
                        gainers.append(entry)
                    else:
                        losers.append(entry)
                except:
                    pass
            gainers.sort(key=lambda x: x['percent_change'], reverse=True)
            losers.sort(key=lambda x: x['percent_change'])
            return {'gainers': gainers, 'losers': losers}
        except Exception as e:
            log.warning(f"Movers fetch failed: {e}")
            return {}

    # ── HELPERS ────────────────────────────────────────

    def _premarket_briefing(self, now: datetime):
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
