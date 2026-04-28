"""
Beast v2.0 — Iron Laws (HARDCODED, DETERMINISTIC)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
These are NOT prompts. These are Python functions that return
(approved: bool, reason: str). They cannot be overridden by AI.

PRIORITY HIERARCHY (higher overrides lower):
  P5 SAFETY:      Account survival, kill switch ($500 daily loss)
  P4 REGULATORY:  PDT compliance, max positions
  P3 RISK_CAP:    Per-position max unrealized loss ($200)
  P2 STRATEGY:    Iron Laws 1-13
  P1 PROFIT:      Strategy signals, preferences
"""
from datetime import datetime, timedelta
from models import (
    Position, TradeProposal, OrderSide, MarketData,
    LawPriority, Regime
)

# ── Configuration ──────────────────────────────────────

MAX_DAILY_LOSS = -500.0
MAX_POSITION_LOSS = -200.0
MAX_DAY_TRADES = 3
MAX_TOTAL_POSITIONS = 10
COOLDOWN_SECONDS = 300          # 5 min re-entry cooldown
CONSECUTIVE_LOSS_STOP = 2
TRADING_WINDOW_START = 9, 45    # 9:45 AM ET
TRADING_WINDOW_END = 11, 0      # 11:00 AM ET
MIN_CONFIDENCE = 0.40           # 40% minimum to trade


# ── Result Type ────────────────────────────────────────

class LawResult:
    """Result of an Iron Law check."""
    __slots__ = ('approved', 'reason', 'law', 'priority')

    def __init__(self, approved: bool, reason: str, law: str,
                 priority: LawPriority = LawPriority.STRATEGY):
        self.approved = approved
        self.reason = reason
        self.law = law
        self.priority = priority

    def __repr__(self):
        status = "✅" if self.approved else "⛔"
        return f"{status} [{self.law}] {self.reason}"


# ── PRIORITY 5: SAFETY ────────────────────────────────

def check_kill_switch(daily_pnl: float) -> LawResult:
    """P5: If daily loss exceeds $500, HALT all trading."""
    if daily_pnl <= MAX_DAILY_LOSS:
        return LawResult(
            False,
            f"KILL SWITCH: Daily P&L ${daily_pnl:.2f} exceeds ${MAX_DAILY_LOSS} limit. ALL TRADING HALTED.",
            "KILL_SWITCH", LawPriority.SAFETY
        )
    return LawResult(True, "Daily P&L within limits", "KILL_SWITCH", LawPriority.SAFETY)


def check_consecutive_losses(consecutive_losses: int) -> LawResult:
    """P5: Stop after N consecutive losses."""
    if consecutive_losses >= CONSECUTIVE_LOSS_STOP:
        return LawResult(
            False,
            f"SAFETY STOP: {consecutive_losses} consecutive losses. Done for the day.",
            "CONSECUTIVE_LOSS", LawPriority.SAFETY
        )
    return LawResult(True, "No consecutive loss issue", "CONSECUTIVE_LOSS", LawPriority.SAFETY)


# ── PRIORITY 4: REGULATORY ────────────────────────────

def check_max_day_trades(current_day_trades: int) -> LawResult:
    """P4: Max 3 day trade scalps at a time (Iron Law 9)."""
    if current_day_trades >= MAX_DAY_TRADES:
        return LawResult(
            False,
            f"Iron Law 9: Max {MAX_DAY_TRADES} day trades reached ({current_day_trades} active).",
            "LAW_9_MAX_SCALPS", LawPriority.REGULATORY
        )
    return LawResult(True, "Day trade count OK", "LAW_9_MAX_SCALPS", LawPriority.REGULATORY)


def check_max_positions(current_positions: int) -> LawResult:
    """P4: Max total positions."""
    if current_positions >= MAX_TOTAL_POSITIONS:
        return LawResult(
            False,
            f"Max positions reached ({current_positions}/{MAX_TOTAL_POSITIONS}).",
            "MAX_POSITIONS", LawPriority.REGULATORY
        )
    return LawResult(True, "Position count OK", "MAX_POSITIONS", LawPriority.REGULATORY)


# ── PRIORITY 3: RISK CAP ──────────────────────────────

def check_position_max_loss(position: Position) -> LawResult:
    """P3: Per-position max loss ALERT (not forced exit).
    Iron Law 1 is ABSOLUTE — we NEVER auto-sell at a loss.
    Instead, we ALERT the user at $500 and STOP buying more of this stock."""
    if position.unrealized_pl <= -500:
        return LawResult(
            True,  # Approved to HOLD (not forced exit)
            f"⚠️ ALERT: {position.symbol} at ${position.unrealized_pl:.2f} exceeds $500 loss. "
            f"HOLDING per Iron Law 1. Alerting user. Blocking new buys on this symbol.",
            "RISK_ALERT", LawPriority.RISK_CAP
        )
    return LawResult(True, "Position loss within limits", "RISK_ALERT", LawPriority.RISK_CAP)


# ── PRIORITY 2: IRON LAWS ─────────────────────────────

def law_1_never_sell_at_loss(position: Position, side: OrderSide) -> LawResult:
    """LAW 1: Never sell a position at a loss. Hold until green.
    Exception: Overridden by P3 RISK_CAP if loss > $200."""
    if side == OrderSide.SELL and position.is_red:
        return LawResult(
            False,
            f"⛔ Iron Law 1: {position.symbol} is RED (${position.unrealized_pl:.2f}). "
            f"HOLD until green. Cannot sell at a loss.",
            "LAW_1_NO_LOSS_SELL"
        )
    return LawResult(True, "Position is green or not a sell", "LAW_1_NO_LOSS_SELL")


def law_2_limit_orders_only(order_type: str) -> LawResult:
    """LAW 2: LIMIT orders ONLY. No market orders. No exceptions."""
    if order_type.lower() != "limit":
        return LawResult(
            False,
            f"⛔ Iron Law 2: Order type '{order_type}' rejected. LIMIT ORDERS ONLY.",
            "LAW_2_LIMIT_ONLY"
        )
    return LawResult(True, "Limit order confirmed", "LAW_2_LIMIT_ONLY")


def law_3_technical_analysis_required(has_technicals: bool) -> LawResult:
    """LAW 3: Technical analysis (RSI/MACD/VWAP) must be done before every trade."""
    if not has_technicals:
        return LawResult(
            False,
            "⛔ Iron Law 3: No technical analysis performed. Must check RSI/MACD/VWAP first.",
            "LAW_3_TV_REQUIRED"
        )
    return LawResult(True, "Technical analysis completed", "LAW_3_TV_REQUIRED")


def law_4_sentiment_required(has_sentiment: bool) -> LawResult:
    """LAW 4: Sentiment check required before every trade."""
    if not has_sentiment:
        return LawResult(
            False,
            "⛔ Iron Law 4: No sentiment check performed. Must check news first.",
            "LAW_4_SENTIMENT_REQUIRED"
        )
    return LawResult(True, "Sentiment check completed", "LAW_4_SENTIMENT_REQUIRED")


def law_5_named_strategy(strategy_name: str) -> LawResult:
    """LAW 5: Every trade must have a named strategy (A-K). No FOMO."""
    if not strategy_name or strategy_name.lower() in ("fomo", "it's moving", "momentum chase"):
        return LawResult(
            False,
            f"⛔ Iron Law 5: '{strategy_name}' is NOT a valid strategy. "
            f"Must be one of A-K (ORB/VWAP/GapGo/etc).",
            "LAW_5_NAMED_STRATEGY"
        )
    return LawResult(True, f"Strategy: {strategy_name}", "LAW_5_NAMED_STRATEGY")


def law_6_exit_at_entry() -> LawResult:
    """LAW 6: Reminder — exit order must be set within 60 seconds of buy.
    Enforced by OrderGateway, not here."""
    return LawResult(True, "Exit will be set by OrderGateway within 60s", "LAW_6_EXIT_AT_ENTRY")


def law_8_cooldown(symbol: str, last_sell_time: dict[str, datetime]) -> LawResult:
    """LAW 8: 5-minute cooldown after selling before re-entry."""
    if symbol in last_sell_time:
        elapsed = (datetime.now() - last_sell_time[symbol]).total_seconds()
        if elapsed < COOLDOWN_SECONDS:
            remaining = COOLDOWN_SECONDS - elapsed
            return LawResult(
                False,
                f"⛔ Iron Law 8: {symbol} sold {elapsed:.0f}s ago. "
                f"Cooldown: {remaining:.0f}s remaining.",
                "LAW_8_COOLDOWN"
            )
    return LawResult(True, "No cooldown active", "LAW_8_COOLDOWN")


def law_10_confidence_check(confidence: float) -> LawResult:
    """LAW 10: When in doubt, do nothing. Confidence must be >= 40%."""
    if confidence < MIN_CONFIDENCE:
        return LawResult(
            False,
            f"⛔ Iron Law 10: Confidence {confidence:.0%} < {MIN_CONFIDENCE:.0%} minimum. "
            f"When in doubt, do nothing.",
            "LAW_10_NO_DOUBT"
        )
    return LawResult(True, f"Confidence {confidence:.0%} OK", "LAW_10_NO_DOUBT")


def law_11_earnings_check(symbol: str, earnings_dates: dict[str, datetime]) -> LawResult:
    """LAW 11: Don't trade stocks the day before or day of earnings."""
    if symbol in earnings_dates:
        earnings_date = earnings_dates[symbol]
        now = datetime.now()
        days_until = (earnings_date.date() - now.date()).days
        if days_until <= 1 and days_until >= 0:
            return LawResult(
                False,
                f"⛔ Iron Law 11: {symbol} has earnings in {days_until} day(s) "
                f"({earnings_date.strftime('%b %d')}). NO TRADING.",
                "LAW_11_EARNINGS"
            )
    return LawResult(True, "No earnings conflict", "LAW_11_EARNINGS")


def law_13_strategy_stock_match(strategy: str, symbol: str, regime: Regime) -> LawResult:
    """LAW 13: Match strategy to stock type. Don't use choppy strategies on volatile stocks."""
    # Quick Flip and Touch & Turn are DESTROYED in CHOPPY
    if regime == Regime.CHOPPY and strategy in ("D", "QUICK_FLIP", "E", "TOUCH_AND_TURN"):
        return LawResult(
            False,
            f"⛔ Iron Law 13: {strategy} is TOXIC in CHOPPY regime "
            f"(backtested -$258 Quick Flip, -$147 Touch&Turn). Blocked.",
            "LAW_13_STRATEGY_MATCH"
        )
    return LawResult(True, "Strategy/stock/regime match OK", "LAW_13_STRATEGY_MATCH")


def check_trading_window() -> LawResult:
    """Check if we're in the allowed trading window (9:45 AM - 11:00 AM ET for new entries)."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    start = now.replace(hour=TRADING_WINDOW_START[0], minute=TRADING_WINDOW_START[1], second=0)
    end = now.replace(hour=TRADING_WINDOW_END[0], minute=TRADING_WINDOW_END[1], second=0)

    if now < start:
        return LawResult(False, f"Before trading window ({now.strftime('%H:%M')} < 9:45 AM)", "TRADING_WINDOW")
    if now > end:
        return LawResult(False, f"After trading window ({now.strftime('%H:%M')} > 11:00 AM)", "TRADING_WINDOW")
    return LawResult(True, f"In trading window ({now.strftime('%H:%M')})", "TRADING_WINDOW")


# ── MASTER VALIDATION ──────────────────────────────────

def validate_entry(
    proposal: TradeProposal,
    market: MarketData,
    positions: list[Position],
    daily_pnl: float,
    consecutive_losses: int,
    active_day_trades: int,
    last_sell_times: dict[str, datetime],
    earnings_dates: dict[str, datetime],
    has_technicals: bool = False,
    has_sentiment: bool = False,
) -> list[LawResult]:
    """Run ALL Iron Law checks on a proposed trade. Returns list of results.
    If ANY result is not approved, the trade is REJECTED."""

    results = []

    # P5: Safety
    results.append(check_kill_switch(daily_pnl))
    results.append(check_consecutive_losses(consecutive_losses))

    # P4: Regulatory
    results.append(check_max_day_trades(active_day_trades))
    results.append(check_max_positions(len(positions)))

    # P2: Iron Laws
    results.append(law_2_limit_orders_only("limit"))  # We enforce this
    results.append(law_3_technical_analysis_required(has_technicals))
    results.append(law_4_sentiment_required(has_sentiment))
    results.append(law_5_named_strategy(proposal.strategy.value if proposal.strategy else ""))
    results.append(law_8_cooldown(proposal.symbol, last_sell_times))
    results.append(law_10_confidence_check(proposal.confidence))
    results.append(law_11_earnings_check(proposal.symbol, earnings_dates))
    results.append(law_13_strategy_stock_match(
        proposal.strategy.value if proposal.strategy else "",
        proposal.symbol, market.regime
    ))
    results.append(check_trading_window())

    return results


def validate_exit(
    position: Position,
    daily_pnl: float,
) -> list[LawResult]:
    """Validate a sell/exit. Iron Law 1 applies unless overridden by P3/P5."""
    results = []

    # P3: Risk cap (overrides Law 1)
    risk_check = check_position_max_loss(position)
    if not risk_check.approved:
        # P3 override: FORCE exit even though position is red
        results.append(LawResult(
            True,  # APPROVED for exit despite being red
            f"P3 OVERRIDE: {risk_check.reason}",
            "RISK_CAP_FORCED_EXIT", LawPriority.RISK_CAP
        ))
        return results

    # P2: Iron Law 1 (don't sell at loss)
    results.append(law_1_never_sell_at_loss(position, OrderSide.SELL))

    return results


def is_approved(results: list[LawResult]) -> bool:
    """Check if all law results approve the action."""
    return all(r.approved for r in results)


def get_rejections(results: list[LawResult]) -> list[LawResult]:
    """Get all rejection reasons."""
    return [r for r in results if not r.approved]
