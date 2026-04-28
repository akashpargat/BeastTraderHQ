"""
Beast v2.0 — Beast Engine (THE BRAIN)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Single long-running process. Wires all components together.
Internal scheduler replaces Windows Task Scheduler (Fix 6).
"""
import logging
import sys
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import Regime, SignalType
from order_gateway import OrderGateway
from data_collector import DataCollector
from technical_analyst import TechnicalAnalyst
from sentiment_analyst import SentimentAnalyst
from regime_detector import RegimeDetector
from monitor import MonitorLoop
from engine.confidence_engine import ConfidenceEngine
from engine.policy_engine import PolicyEngine
from engine.bull_bear_debate import BullBearDebate

ET = ZoneInfo("America/New_York")

# ── Watchlists ─────────────────────────────────────────

OFFENSE_ROSTER = ['COIN', 'TSLA', 'META', 'MSTR']
DEFENSE_ROSTER = ['CAT', 'ORCL', 'XOM', 'COST', 'LMT', 'RTX']
MAG7 = ['AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA', 'TSLA']
BLUE_CHIPS = ['GOOGL', 'MSFT', 'AAPL', 'AMZN', 'CRM', 'NOW', 'NOK']
ENERGY = ['DVN', 'OXY', 'XOM', 'CVX', 'HAL']
PAST_WINNERS = ['NOK', 'GOOGL', 'CRM', 'META', 'MSFT', 'NOW', 'AMD', 'NVDA']

# ── Logging ────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('beast.log', encoding='utf-8'),
    ]
)
log = logging.getLogger('Beast')


class BeastEngine:
    """The autonomous trading beast. Single process, internal scheduler."""

    def __init__(self):
        load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

        api_key = os.getenv('ALPACA_API_KEY', '')
        secret = os.getenv('ALPACA_SECRET_KEY', '')
        claude_key = os.getenv('ANTHROPIC_API_KEY', '')

        if not api_key or not secret:
            raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY required in .env")

        # Initialize all components
        self.gateway = OrderGateway(api_key, secret, paper=True)
        self.data = DataCollector(api_key, secret)
        self.technicals = TechnicalAnalyst()
        self.sentiment = SentimentAnalyst()
        self.regime = RegimeDetector()
        self.confidence = ConfidenceEngine()
        self.policy = PolicyEngine()
        self.debate = BullBearDebate(claude_key)
        self.monitor = MonitorLoop(self.gateway, self.data, self.policy)

        self._running = False
        self._last_scan_time = datetime.min
        self._today_date = None

        log.info("🦍 Beast Engine v2.0 initialized")
        log.info(f"   Claude AI: {'✅ connected' if self.debate.is_available else '❌ offline (deterministic mode)'}")

    # ── Main Loop ──────────────────────────────────────

    def run(self):
        """Main event loop. Runs forever."""
        self._running = True
        log.info("🦍 BEAST MODE ACTIVATED — autonomous trading started")

        try:
            while self._running:
                now = datetime.now(ET)

                # New day reset
                if self._today_date != now.date():
                    self._new_day(now)

                if self.data.is_market_open():
                    self._market_tick(now)
                else:
                    self._off_hours_tick(now)

                time.sleep(5)  # 5-second heartbeat

        except KeyboardInterrupt:
            log.info("🛑 Beast Engine stopped by user")
        except Exception as e:
            log.critical(f"💀 Beast Engine crashed: {e}", exc_info=True)
        finally:
            self._running = False

    def _new_day(self, now: datetime):
        """Reset for new trading day."""
        self._today_date = now.date()
        self.policy.reset_day()
        self.monitor.reset_day()
        log.info(f"🌅 New trading day: {now.strftime('%A %B %d, %Y')}")

        # Load earnings calendar
        all_symbols = list(set(OFFENSE_ROSTER + DEFENSE_ROSTER + MAG7 + BLUE_CHIPS))
        self.policy.earnings_dates = self.data.get_earnings_dates(all_symbols)
        flagged = {s: d.strftime('%b %d') for s, d in self.policy.earnings_dates.items()
                   if (d.date() - now.date()).days <= 1}
        if flagged:
            log.warning(f"⚠️ EARNINGS ALERT: {flagged}")

    # ── Market Hours Tick ──────────────────────────────

    def _market_tick(self, now: datetime):
        """Called every 5 seconds during market hours."""
        # Monitor loop always runs (trailing stops, partial exits)
        self.monitor.tick()

        # Scheduled scans at specific times
        hour, minute = now.hour, now.minute

        # Pre-market scan (9:15-9:29)
        if hour == 9 and 15 <= minute < 30:
            self._run_scan_if_due(now, "pre_market", interval=300)

        # ORB analysis (9:45)
        elif hour == 9 and 45 <= minute < 50:
            self._run_scan_if_due(now, "orb_scan", interval=300)

        # Mid-morning rebalance (10:15)
        elif hour == 10 and 15 <= minute < 20:
            self._run_scan_if_due(now, "mid_morning", interval=300)

        # Last entries (10:45)
        elif hour == 10 and 45 <= minute < 50:
            self._run_scan_if_due(now, "last_entries", interval=300)

        # Every 2 hours for swing positions (Nate Herk approach)
        else:
            self._run_scan_if_due(now, "swing_check", interval=7200)

    def _run_scan_if_due(self, now: datetime, scan_type: str, interval: int):
        """Run a scan if enough time has passed."""
        elapsed = (now - self._last_scan_time).total_seconds()
        if elapsed < interval:
            return

        log.info(f"📡 Running scan: {scan_type}")
        self._last_scan_time = now

        try:
            self._full_cycle(scan_type)
        except Exception as e:
            log.error(f"Scan {scan_type} failed: {e}", exc_info=True)

    # ── Full Analysis Cycle ────────────────────────────

    def _full_cycle(self, scan_type: str):
        """Complete analysis cycle: data → technicals → sentiment → confidence → policy → execute."""

        # 1. Get positions and market data
        positions = self.gateway.get_positions()
        market = self.data.get_market_data(positions)

        # 2. Detect regime
        current_regime = self.regime.detect(market.spy_change_pct)
        market.regime = current_regime
        log.info(f"📊 Regime: {current_regime.value} (SPY {market.spy_change_pct:+.2%})")

        # 3. Select watchlist based on regime
        if current_regime == Regime.RED_ALERT:
            log.warning("🔴 RED ALERT — monitoring only, no new entries")
            return

        watchlist = self._get_watchlist(current_regime, positions)

        # 4. Run technicals on all stocks
        tech_results = {}
        for symbol in watchlist:
            bars = self.data.get_bars(symbol, '5Min', 50)
            if bars:
                quote = self.data.get_quote(symbol)
                price = quote.last if quote else 0
                tech_results[symbol] = self.technicals.analyze(symbol, bars, price)

        # 5. Run sentiment on all stocks
        sent_results = {}
        market_sentiment = self.sentiment.analyze_market()
        for symbol in watchlist:
            sent_results[symbol] = self.sentiment.analyze(symbol)

        # 6. Confidence Engine scores
        prices = {}
        for symbol in watchlist:
            q = self.data.get_quote(symbol)
            if q:
                prices[symbol] = q.last

        scored = self.confidence.score_batch(
            watchlist, tech_results, sent_results, current_regime, prices
        )

        # 7. Bull/Bear debate on top candidates (optional, non-blocking)
        for result in scored[:3]:  # Top 3 only to save API calls
            if result.signal in (SignalType.STRONG_BUY, SignalType.BUY):
                tech = tech_results.get(result.symbol)
                sent = sent_results.get(result.symbol)
                if tech and sent:
                    bull, bear, ai_conf = self.debate.debate(
                        result.symbol, tech, sent, current_regime,
                        prices.get(result.symbol, 0)
                    )
                    result.bull_case = bull
                    result.bear_case = bear
                    # Blend AI confidence with engine confidence
                    if ai_conf != 0.5:  # Only if AI actually gave an opinion
                        result.overall_confidence = (
                            result.overall_confidence * 0.7 + ai_conf * 0.3
                        )

        # 8. Policy Engine evaluates and approves/rejects
        for result in scored:
            if result.signal in (SignalType.STRONG_BUY, SignalType.BUY):
                verdict = self.policy.evaluate_entry(
                    result, market, positions, market_sentiment.total_score
                )
                if verdict.approved and verdict.proposal:
                    # EXECUTE!
                    log.info(f"🎯 EXECUTING: {verdict.proposal.symbol} — "
                           f"{verdict.proposal.strategy.value} "
                           f"({verdict.proposal.confidence:.0%})")

                    # Split entry: half scalp, half runner
                    scalp, runner = self.gateway.place_split_entry(
                        verdict.proposal, market, positions,
                        self.policy.daily_pnl, self.policy.consecutive_losses,
                        self.policy.active_day_trades, self.policy.earnings_dates,
                        has_technicals=True, has_sentiment=True,
                    )
                    if scalp.state.value == 'sent':
                        self.monitor.mark_day_trade(verdict.proposal.symbol)
                        self.policy.active_day_trades += 1

        # 9. Log dashboard
        self._log_dashboard(market, positions, scored, market_sentiment)

    # ── Helpers ─────────────────────────────────────────

    def _get_watchlist(self, regime: Regime, positions: list) -> list[str]:
        """Build watchlist: regime roster + held positions + blue chips."""
        held = [p.symbol for p in positions]
        if regime == Regime.BULL:
            base = OFFENSE_ROSTER + MAG7
        elif regime == Regime.BEAR:
            base = DEFENSE_ROSTER
        else:
            base = DEFENSE_ROSTER + BLUE_CHIPS

        return list(set(base + held + BLUE_CHIPS))

    def _log_dashboard(self, market, positions, scored, mkt_sentiment):
        """Log a beast mode dashboard to console and file."""
        now = datetime.now(ET)
        total_pnl = sum(p.unrealized_pl for p in positions)

        lines = [
            f"\n🦍 BEAST ENGINE — {now.strftime('%H:%M:%S %Z')}",
            f"{'━' * 50}",
            f"REGIME: {market.regime.value} | SPY ${market.spy_price:.2f} ({market.spy_change_pct:+.2%})",
            f"SENTIMENT: {mkt_sentiment.total_score}/15 | EQUITY: ${market.account_equity:,.2f}",
            f"{'━' * 50}",
        ]

        for p in positions:
            emoji = "🟢" if p.is_green else "🔴"
            lines.append(f"  {emoji} {p.symbol:6s} {p.qty:3d}x ${p.current_price:8.2f} "
                        f"P&L: ${p.unrealized_pl:+8.2f} ({p.unrealized_pl_pct:+.2%})")

        lines.append(f"{'━' * 50}")
        lines.append(f"TOTAL P&L: ${total_pnl:+.2f} | "
                     f"Bell: {self.policy.bell_curve:.0%} | "
                     f"Day trades: {self.policy.active_day_trades}/3")

        # Top opportunities
        top = [s for s in scored if s.signal in (SignalType.STRONG_BUY, SignalType.BUY)][:3]
        if top:
            lines.append(f"\n🎯 TOP OPPORTUNITIES:")
            for s in top:
                strat = s.best_strategy.value if s.best_strategy else "?"
                lines.append(f"  {s.symbol:6s} {s.overall_confidence:.0%} "
                           f"[{s.signal.value}] Strategy {strat}")

        dashboard = "\n".join(lines)
        log.info(dashboard)

    # ── Off-Hours ──────────────────────────────────────

    def _off_hours_tick(self, now: datetime):
        """Off-hours: just check swing positions every 60 seconds."""
        if (now - self._last_scan_time).total_seconds() < 60:
            return

        self._last_scan_time = now
        positions = self.gateway.get_positions()
        if positions:
            total = sum(p.unrealized_pl for p in positions)
            log.debug(f"💤 Off-hours: {len(positions)} positions, P&L: ${total:+.2f}")

    def stop(self):
        """Graceful shutdown."""
        self._running = False
        self.monitor.stop()
        log.info("🛑 Beast Engine shutting down")
