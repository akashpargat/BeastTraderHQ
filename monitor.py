"""
Beast v2.0 — Monitor Loop (5-second heartbeat)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Runs in the SAME process as the beast engine (not separate).
Manages trailing stops, partial exits, and kill switch.
ALL exit orders go through OrderGateway (single writer).
"""
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from models import Position, Regime

log = logging.getLogger('Beast.Monitor')
ET = ZoneInfo("America/New_York")

# Trailing stop tiers (from skill file)
TRAILING_TIERS = [
    {'range': (0, 5),    'type': 'fixed',     'value': 10.0, 'check_sec': 30},
    {'range': (5, 20),   'type': 'trail_pct',  'value': 0.0025, 'check_sec': 45},
    {'range': (20, 50),  'type': 'trail_pct',  'value': 0.0030, 'check_sec': 60},
    {'range': (50, 100), 'type': 'trail_pct',  'value': 0.0050, 'check_sec': 45, 'partial': 0.25},
    {'range': (100, float('inf')), 'type': 'trail_pct', 'value': 0.010, 'check_sec': 45, 'partial': 0.25},
]

PARTIAL_MILESTONES = [20, 50, 100]  # Sell 25% at each milestone

# Hard close time (11:00 AM ET for day trades)
HARD_CLOSE_HOUR = 11
HARD_CLOSE_MINUTE = 0


class MonitorLoop:
    """5-second position monitor with adaptive trailing stops."""

    def __init__(self, order_gateway, data_collector, policy_engine):
        self.gateway = order_gateway
        self.data = data_collector
        self.policy = policy_engine
        self.peak_prices: dict[str, float] = {}
        self.partial_exits_done: dict[str, set] = {}  # symbol → set of milestones hit
        self.day_trade_symbols: set[str] = set()  # Symbols that are day trades (close at 11 AM)
        self._running = False

    def start(self):
        """Start the monitor loop (called by beast engine scheduler)."""
        self._running = True
        log.info("🫀 Monitor loop started (5-sec heartbeat)")

    def stop(self):
        self._running = False
        log.info("💤 Monitor loop stopped")

    def tick(self):
        """One tick of the monitor. Called every 5 seconds by the scheduler."""
        if not self._running:
            return

        positions = self.gateway.get_positions()
        if not positions:
            return

        now = datetime.now(ET)

        # Check Iron Law 6 compliance (exit orders set within 60s)
        violations = self.gateway.check_exit_timers()
        for sym in violations:
            log.error(f"⛔ LAW 6 VIOLATION: {sym} — auto-setting emergency exit")
            self._emergency_exit(sym, positions)

        for pos in positions:
            self._check_position(pos, now)

        # Hard close at 11:00 AM
        if now.hour == HARD_CLOSE_HOUR and now.minute >= HARD_CLOSE_MINUTE:
            self._hard_close(positions)

        # Sync order states with broker
        self.gateway.sync_orders()

    def _check_position(self, pos: Position, now: datetime):
        """Check trailing stops and partial exits for one position."""
        symbol = pos.symbol
        profit = pos.unrealized_pl

        # Track peak price
        if symbol not in self.peak_prices or pos.current_price > self.peak_prices[symbol]:
            self.peak_prices[symbol] = pos.current_price

        peak = self.peak_prices[symbol]

        # Determine which tier we're in
        tier = self._get_tier(profit)
        if not tier:
            return

        # Check for partial exit milestones
        if symbol not in self.partial_exits_done:
            self.partial_exits_done[symbol] = set()

        for milestone in PARTIAL_MILESTONES:
            if profit >= milestone and milestone not in self.partial_exits_done[symbol]:
                partial_qty = max(1, pos.qty // 4)  # 25% of position
                if partial_qty > 0 and pos.qty > partial_qty:
                    # Check if selling is allowed (Iron Law 1 — position is green)
                    verdict = self.policy.evaluate_exit(pos)
                    if verdict.approved:
                        sell_price = round(pos.current_price, 2)  # Avoid sub-penny
                        self.gateway.place_sell(
                            symbol, partial_qty, sell_price,
                            reason=f"Partial exit at +${milestone} milestone"
                        )
                        self.partial_exits_done[symbol].add(milestone)
                        log.info(f"💰 PARTIAL: Sold {partial_qty}x {symbol} "
                               f"at +${profit:.2f} (${milestone} milestone)")

        # Check trailing stop
        if tier['type'] == 'fixed':
            # Fixed $10 stop from entry
            loss_from_entry = pos.unrealized_pl
            if loss_from_entry <= -tier['value']:
                verdict = self.policy.evaluate_exit(pos)
                if verdict.approved:
                    sell_price = round(pos.current_price, 2)  # Avoid sub-penny
                    self.gateway.place_sell(
                        symbol, pos.qty, sell_price,
                        reason=f"$10 fixed stop hit (P&L: ${profit:.2f})"
                    )
                    self.policy.record_loss()

        elif tier['type'] == 'trail_pct':
            trail_pct = tier['value']
            trail_price = peak * (1 - trail_pct)

            if pos.current_price <= trail_price:
                verdict = self.policy.evaluate_exit(pos)
                if verdict.approved:
                    sell_price = round(pos.current_price, 2)  # Avoid sub-penny
                    self.gateway.place_sell(
                        symbol, pos.qty, sell_price,
                        reason=f"Trail stop hit ({trail_pct:.2%} from peak ${peak:.2f})"
                    )
                    self.policy.record_win() if profit > 0 else self.policy.record_loss()

    def _get_tier(self, profit: float) -> dict:
        for tier in TRAILING_TIERS:
            low, high = tier['range']
            if low <= profit < high:
                return tier
        return TRAILING_TIERS[-1] if profit >= 100 else TRAILING_TIERS[0]

    def _hard_close(self, positions: list[Position]):
        """Close all day trade positions at 11:00 AM."""
        for pos in positions:
            if pos.symbol in self.day_trade_symbols:
                if pos.is_green:
                    self.gateway.place_sell(
                        pos.symbol, pos.qty, pos.current_price,
                        reason="11:00 AM hard close (day trade)"
                    )
                    log.info(f"⏰ HARD CLOSE: {pos.symbol} at +${pos.unrealized_pl:.2f}")
                else:
                    log.warning(f"⏰ 11 AM: {pos.symbol} is RED (${pos.unrealized_pl:.2f}). "
                              f"Iron Law 1: converting to swing hold.")

    def _emergency_exit(self, symbol: str, positions: list[Position]):
        """Emergency exit for Law 6 violations — set a reasonable limit sell."""
        for pos in positions:
            if pos.symbol == symbol and pos.is_green:
                target = pos.current_price * 1.003  # +0.3% from current
                self.gateway.place_sell(symbol, pos.qty, target,
                                       reason="Law 6 emergency exit (auto-set)")

    def mark_day_trade(self, symbol: str):
        """Mark a symbol as a day trade (will be closed at 11 AM)."""
        self.day_trade_symbols.add(symbol)

    def reset_day(self):
        """Reset for new trading day."""
        self.peak_prices.clear()
        self.partial_exits_done.clear()
        self.day_trade_symbols.clear()
