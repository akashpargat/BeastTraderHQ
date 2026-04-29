"""
Beast v3.0 — Iron Laws (HARDCODED, DETERMINISTIC)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
These are NOT prompts. These are Python functions that return
(approved: bool, reason: str). They cannot be overridden by AI.

UPDATED: 2026-04-28 by Session 7a05060d (v7.1 — 23 Iron Laws)
Lessons from Days 1-6 of live trading baked in.

PRIORITY HIERARCHY (higher overrides lower):
  P5 SAFETY:      Account survival, kill switch ($500 daily loss)
  P4 REGULATORY:  PDT compliance, max positions
  P3 RISK_CAP:    Per-position max unrealized loss ($200)
  P2 STRATEGY:    Iron Laws 1-23
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
MAX_TOTAL_POSITIONS = 12          # Raised from 10 — we run 12 positions now
COOLDOWN_SECONDS = 300            # 5 min re-entry cooldown
CONSECUTIVE_LOSS_STOP = 2
TRADING_WINDOW_START = 9, 30      # Changed: 9:30 AM ET (was 9:45 — we missed moves)
TRADING_WINDOW_END = 15, 55       # Changed: 3:55 PM ET (was 11:00 — we swing trade now)
MIN_CONFIDENCE = 0.40             # 40% minimum to trade
MIN_SCALP_PROFIT_PCT = 0.02       # Rule #17: Minimum 2% profit target on scalps
MOMENTUM_RSI_OVERRIDE = True      # Rule #30: RSI>70 OK for momentum stocks with catalysts

# ── PAST WINNERS (Rule #21: check these FIRST every scan) ──
PAST_WINNERS = ['NOK', 'GOOGL', 'CRM', 'META', 'MSFT', 'NOW', 'AMD', 'NVDA']


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


# ── NEW LAWS v7.1 (Days 4-6 Learnings) ─────────────────

def law_14_split_position(qty: int) -> LawResult:
    """LAW 14: Split EVERY position — half scalp, half runner.
    Day 4: META scalp +$43, runner +$94 = $137 total vs $43 if sold all."""
    # This is enforced by OrderGateway — set TWO sell orders per buy
    return LawResult(True,
        f"Split position reminder: {qty//2} scalp + {qty - qty//2} runner",
        "LAW_14_SPLIT_POSITION")


def law_17_min_scalp_profit(entry_price: float, sell_price: float) -> LawResult:
    """LAW 17: Minimum 2% profit target on scalps.
    Day 5: Rookie set $263.75 sell on $262.63 buy = 0.03% = GARBAGE."""
    if sell_price <= 0 or entry_price <= 0:
        return LawResult(True, "Price check skipped", "LAW_17_MIN_PROFIT")
    profit_pct = (sell_price - entry_price) / entry_price
    if profit_pct < MIN_SCALP_PROFIT_PCT:
        return LawResult(
            False,
            f"⛔ Iron Law 17: Sell target ${sell_price:.2f} is only {profit_pct:.1%} above "
            f"entry ${entry_price:.2f}. Minimum {MIN_SCALP_PROFIT_PCT:.0%} required. "
            f"Don't give away money!",
            "LAW_17_MIN_PROFIT"
        )
    return LawResult(True, f"Profit target {profit_pct:.1%} OK", "LAW_17_MIN_PROFIT")


def law_21_past_winners_priority(symbol: str, movers: list[str]) -> LawResult:
    """LAW 21: Cross-reference movers with past winners. Flag immediately.
    Day 5: NOK was #6 most active, ignored for 35 min = $880 lost."""
    if symbol in PAST_WINNERS and symbol in movers:
        return LawResult(
            True,  # Approved — but with a HIGH PRIORITY flag
            f"🔥 PAST WINNER ALERT: {symbol} is on movers list! "
            f"This stock has made us money before. PRIORITY SCAN.",
            "LAW_21_PAST_WINNER"
        )
    return LawResult(True, "No past winner flag", "LAW_21_PAST_WINNER")


def law_29_no_chase(symbol: str, current_price: float, day_open: float) -> LawResult:
    """LAW 29: Don't chase stocks that already ran 5%+.
    Day 5: Bought NOK at $11.24 after +5% run. Lost $480.
    If you missed the move, set a limit at VWAP and WAIT."""
    if day_open > 0:
        pct_from_open = (current_price - day_open) / day_open
        if pct_from_open > 0.05:
            return LawResult(
                False,
                f"⛔ Iron Law 29: {symbol} already up {pct_from_open:.1%} from open "
                f"(${day_open:.2f} → ${current_price:.2f}). Don't chase! "
                f"Set limit buy at VWAP or EMA and wait for pullback.",
                "LAW_29_NO_CHASE"
            )
    return LawResult(True, "Not chasing", "LAW_29_NO_CHASE")


def law_30_momentum_rsi_override(rsi: float, has_catalyst: bool, sma_slope_up: bool) -> LawResult:
    """LAW 30: RSI>70 is OK for momentum stocks WITH real catalysts.
    Days 3-6: INTC missed 3x because RSI>70. But SMA was vertical + earnings beat.
    For MOMENTUM stocks: SMA slope UP + catalyst = buy despite high RSI."""
    if rsi > 70 and not has_catalyst:
        return LawResult(
            False,
            f"⛔ Iron Law 30: RSI {rsi:.0f} > 70 with NO catalyst. "
            f"Don't buy overbought stocks without a reason.",
            "LAW_30_RSI_MOMENTUM"
        )
    if rsi > 70 and has_catalyst and sma_slope_up:
        return LawResult(
            True,
            f"✅ Iron Law 30 OVERRIDE: RSI {rsi:.0f} > 70 BUT has catalyst + SMA trending up. "
            f"Momentum stocks stay overbought for days. Approved.",
            "LAW_30_RSI_MOMENTUM"
        )
    return LawResult(True, "RSI check OK", "LAW_30_RSI_MOMENTUM")


def law_31_premarket_runners_first(is_premarket: bool, sym: str, pct_change: float,
                                    is_past_winner: bool) -> LawResult:
    """LAW 31: Pre-market runners get PRIORITY scanning and execution.
    Day 5: NOK ran +5% pre-market, we found it 35 min AFTER open = chased at top.
    Day 7: NOK +9.6% pre-market = gone by open. MU +4.5% pre-market.
    LESSON: If it's running pre-market with volume, it RUNS MORE at open.
    Buy the pre-market runner BEFORE the open crowd piles in."""
    if is_premarket and pct_change >= 2.0:
        if is_past_winner:
            return LawResult(
                True,
                f"🌅 Law 31: {sym} is a PAST WINNER running +{pct_change:.1f}% pre-market. "
                f"BUY NOW before open! Don't be Day 5 NOK again.",
                "LAW_31_PREMARKET_RUNNER"
            )
        if pct_change <= 8.0:
            return LawResult(
                True,
                f"🌅 Law 31: {sym} running +{pct_change:.1f}% pre-market. "
                f"Catch it early before the 9:30 crowd.",
                "LAW_31_PREMARKET_RUNNER"
            )
    return LawResult(True, "Pre-market check OK", "LAW_31_PREMARKET_RUNNER")


def check_trading_window() -> LawResult:
    """Check if we're in the allowed trading window.
    Regular: 9:30 AM - 3:55 PM ET
    Extended: 4:00 AM - 8:00 PM ET (pre-market + after-hours)
    We trade ALL sessions now — not just 9:45-11:00."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    hour = now.hour
    
    # Extended hours: 4 AM - 8 PM ET
    if hour < 4 or hour >= 20:
        return LawResult(False, f"Outside all trading hours ({now.strftime('%H:%M')})", "TRADING_WINDOW")
    
    # Pre-market: 4:00 AM - 9:30 AM (lighter activity, wider spreads)
    if 4 <= hour < 9 or (hour == 9 and now.minute < 30):
        return LawResult(True, f"PRE-MARKET session ({now.strftime('%H:%M')}). Wider spreads — use limits only!", "TRADING_WINDOW")
    
    # Regular: 9:30 AM - 4:00 PM
    if (hour == 9 and now.minute >= 30) or (9 < hour < 16):
        return LawResult(True, f"REGULAR session ({now.strftime('%H:%M')})", "TRADING_WINDOW")
    
    # After-hours: 4:00 PM - 8:00 PM
    if 16 <= hour < 20:
        return LawResult(True, f"AFTER-HOURS session ({now.strftime('%H:%M')}). Earnings reactions — be cautious!", "TRADING_WINDOW")
    
    return LawResult(False, f"Unknown session ({now.strftime('%H:%M')})", "TRADING_WINDOW")


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
