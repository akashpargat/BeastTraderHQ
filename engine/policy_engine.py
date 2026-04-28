"""
Beast v2.0 — Policy Engine (DETERMINISTIC)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The single decision-maker. Takes signals from all analyzers,
applies Iron Laws, and produces approved/rejected verdicts.
NO AI in this module. Pure deterministic logic.
"""
import logging
from datetime import datetime
from models import (
    ConfidenceResult, TradeProposal, PolicyVerdict, Position,
    MarketData, OrderSide, SignalType, Regime, LawPriority
)
from iron_laws import (
    validate_entry, validate_exit, is_approved, get_rejections,
    check_kill_switch, check_consecutive_losses
)

log = logging.getLogger('Beast.PolicyEngine')

# Position sizing
BASE_POSITION_PCT = 0.05    # 5% of equity per position
SENTIMENT_MULTIPLIERS = {
    'aggressive': 1.5,    # sentiment +5 to +10
    'normal': 1.0,        # sentiment +1 to +4
    'cautious': 0.8,      # sentiment 0
    'defensive': 0.5,     # sentiment -1 to -4
    'abort': 0.0,         # sentiment -5 to -10
}

# Bell curve
BELL_START = 0.50
BELL_WIN_STEP = 0.15
BELL_LOSS_STEP = 0.15
BELL_MAX = 1.0
BELL_MIN = 0.25


class PolicyEngine:
    """Deterministic decision engine. Applies Iron Laws to signals."""

    def __init__(self):
        self.bell_curve = BELL_START
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        self.active_day_trades = 0
        self.last_sell_times: dict[str, datetime] = {}
        self.earnings_dates: dict[str, datetime] = {}
        self.halted = False

    def evaluate_entry(self, result: ConfidenceResult,
                       market: MarketData,
                       positions: list[Position],
                       sentiment_total: int = 0) -> PolicyVerdict:
        """Evaluate whether to enter a trade based on confidence result."""

        # Check if halted
        if self.halted:
            return PolicyVerdict(
                approved=False,
                rejection_reason="Trading HALTED (kill switch or consecutive losses)",
                priority=LawPriority.SAFETY,
            )

        # Safety checks first
        kill = check_kill_switch(self.daily_pnl)
        if not kill.approved:
            self.halted = True
            return PolicyVerdict(approved=False, rejection_reason=kill.reason,
                               priority=LawPriority.SAFETY)

        loss_check = check_consecutive_losses(self.consecutive_losses)
        if not loss_check.approved:
            self.halted = True
            return PolicyVerdict(approved=False, rejection_reason=loss_check.reason,
                               priority=LawPriority.SAFETY)

        # RED_ALERT = no new entries
        if market.regime == Regime.RED_ALERT:
            return PolicyVerdict(
                approved=False,
                rejection_reason="RED ALERT regime — no new entries allowed",
                priority=LawPriority.STRATEGY,
            )

        # Confidence too low
        if result.signal in (SignalType.NO_TRADE, SignalType.HOLD):
            return PolicyVerdict(
                approved=False,
                rejection_reason=f"Signal is {result.signal.value} "
                                f"(confidence {result.overall_confidence:.0%})",
                priority=LawPriority.STRATEGY,
            )

        # No strategy matched
        if not result.best_strategy:
            return PolicyVerdict(
                approved=False,
                rejection_reason="No strategy matched (Iron Law 5: named strategy required)",
                law_violated="LAW_5",
                priority=LawPriority.STRATEGY,
            )

        # Calculate position size
        qty, limit_price = self._calculate_position(
            result, market, sentiment_total
        )
        if qty <= 0:
            return PolicyVerdict(
                approved=False,
                rejection_reason="Position size calculated as 0 (sentiment abort or sizing issue)",
                priority=LawPriority.STRATEGY,
            )

        # Build proposal
        proposal = TradeProposal(
            symbol=result.symbol,
            side=OrderSide.BUY,
            qty=qty,
            limit_price=limit_price,
            strategy=result.best_strategy,
            confidence=result.overall_confidence,
            reason=f"Confidence {result.overall_confidence:.0%}, "
                   f"Strategy {result.best_strategy.value}",
            target_price=self._calculate_target(limit_price, result.best_strategy),
            stop_price=limit_price - 10.0 / qty,  # $10 max loss
        )

        # Run Iron Laws validation
        results = validate_entry(
            proposal=proposal,
            market=market,
            positions=positions,
            daily_pnl=self.daily_pnl,
            consecutive_losses=self.consecutive_losses,
            active_day_trades=self.active_day_trades,
            last_sell_times=self.last_sell_times,
            earnings_dates=self.earnings_dates,
            has_technicals=result.technical is not None,
            has_sentiment=result.sentiment is not None,
        )

        if is_approved(results):
            log.info(f"✅ APPROVED: {proposal.symbol} {proposal.qty}x @ "
                    f"${proposal.limit_price:.2f} ({result.best_strategy.value})")
            return PolicyVerdict(approved=True, proposal=proposal)
        else:
            rejections = get_rejections(results)
            reason = " | ".join(r.reason for r in rejections)
            law = rejections[0].law if rejections else ""
            log.warning(f"🚫 REJECTED: {proposal.symbol} — {reason}")
            return PolicyVerdict(
                approved=False,
                proposal=proposal,
                rejection_reason=reason,
                law_violated=law,
                priority=rejections[0].priority if rejections else LawPriority.STRATEGY,
            )

    def evaluate_exit(self, position: Position) -> PolicyVerdict:
        """Evaluate whether to exit a position."""
        results = validate_exit(position, self.daily_pnl)

        if is_approved(results):
            return PolicyVerdict(approved=True)
        else:
            rejections = get_rejections(results)
            reason = " | ".join(r.reason for r in rejections)
            return PolicyVerdict(approved=False, rejection_reason=reason)

    # ── Position Sizing ────────────────────────────────

    def _calculate_position(self, result: ConfidenceResult,
                           market: MarketData, sentiment_total: int) -> tuple[int, float]:
        """Calculate qty and limit price."""
        equity = market.account_equity
        if equity <= 0:
            return 0, 0

        # Base allocation
        base_dollars = equity * BASE_POSITION_PCT

        # Bell curve adjustment
        scaled = base_dollars * self.bell_curve

        # Sentiment multiplier
        if sentiment_total >= 5:
            mult = SENTIMENT_MULTIPLIERS['aggressive']
        elif sentiment_total >= 1:
            mult = SENTIMENT_MULTIPLIERS['normal']
        elif sentiment_total == 0:
            mult = SENTIMENT_MULTIPLIERS['cautious']
        elif sentiment_total >= -4:
            mult = SENTIMENT_MULTIPLIERS['defensive']
        else:
            return 0, 0  # ABORT

        final_dollars = scaled * mult

        # Get price from technicals or confidence result
        price = 0
        if result.technical and result.technical.vwap > 0:
            price = result.technical.vwap
        if price <= 0:
            return 0, 0

        qty = int(final_dollars / price)

        # Enforce min stop room ($0.50/share)
        max_qty_for_stop = int(10.0 / 0.50)  # $10 stop / $0.50 = 20 shares max for cheap stocks
        if price < 100:
            qty = min(qty, max_qty_for_stop)

        return max(1, qty), round(price, 2)

    def _calculate_target(self, entry: float, strategy: Strategy) -> float:
        """Calculate target price based on strategy."""
        # Conservative targets by strategy
        targets = {
            Strategy.ORB_BREAKOUT: 0.005,      # 0.5%
            Strategy.VWAP_BOUNCE: 0.004,        # 0.4%
            Strategy.GAP_AND_GO: 0.006,         # 0.6%
            Strategy.QUICK_FLIP: 0.003,         # 0.3%
            Strategy.TOUCH_AND_TURN: 0.004,     # 0.4%
            Strategy.FAIR_VALUE_GAP: 0.005,     # 0.5%
            Strategy.RED_TO_GREEN: 0.005,       # 0.5%
            Strategy.FIVE_MIN_SCALP: 0.003,     # 0.3%
            Strategy.BLUE_CHIP_REVERSION: 0.008, # 0.8%
            Strategy.SMA_TREND_FOLLOW: 0.006,   # 0.6%
            Strategy.SECTOR_MOMENTUM: 0.005,    # 0.5%
        }
        pct = targets.get(strategy, 0.005)
        return round(entry * (1 + pct), 2)

    # ── Bell Curve Updates ─────────────────────────────

    def record_win(self):
        self.consecutive_wins += 1
        self.consecutive_losses = 0
        self.bell_curve = min(BELL_MAX, self.bell_curve + BELL_WIN_STEP)
        log.info(f"🟢 Win streak: {self.consecutive_wins} | Bell curve: {self.bell_curve:.0%}")

    def record_loss(self):
        self.consecutive_losses += 1
        self.consecutive_wins = 0
        self.bell_curve = max(BELL_MIN, self.bell_curve - BELL_LOSS_STEP)
        log.info(f"🔴 Loss streak: {self.consecutive_losses} | Bell curve: {self.bell_curve:.0%}")
        if self.consecutive_losses >= 2:
            self.halted = True
            log.warning("⛔ 2 consecutive losses — HALTED for the day")

    def update_daily_pnl(self, pnl: float):
        self.daily_pnl = pnl
        if pnl <= -500:
            self.halted = True
            log.warning(f"⛔ KILL SWITCH: Daily P&L ${pnl:.2f} — HALTED")

    def reset_day(self):
        """Reset daily state for new trading day."""
        self.daily_pnl = 0.0
        self.active_day_trades = 0
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.bell_curve = BELL_START
        self.halted = False
        self.last_sell_times.clear()
        log.info("🌅 New trading day — all daily counters reset")
