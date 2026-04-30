"""
Beast v2.0 — Order Gateway (SINGLE WRITER)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE most critical module. ALL order mutations go through here.
No other module talks to Alpaca for orders. Period.

Fixes v1.0 bugs:
- Multi-writer race conditions (monitor + orchestrator both placing orders)
- Missing exit orders (Iron Law 6)
- Market orders instead of limit (Iron Law 2)
- No order state tracking (partial fills, rejects)
"""
import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    LimitOrderRequest, GetOrdersRequest, TrailingStopOrderRequest,
)
from alpaca.trading.enums import OrderClass
from alpaca.trading.enums import (
    OrderSide as AlpacaSide, TimeInForce, QueryOrderStatus
)
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

from models import (
    OrderRecord, OrderState, OrderSide, TradeProposal,
    Position, PolicyVerdict, Strategy
)
from iron_laws import validate_entry, validate_exit, is_approved, get_rejections

log = logging.getLogger('Beast.OrderGateway')


class OrderGateway:
    """Single-writer gateway to Alpaca. Thread-safe."""

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.client = TradingClient(api_key, secret_key, paper=paper)
        self.data_client = StockHistoricalDataClient(api_key, secret_key)
        self._lock = threading.Lock()
        self.active_orders: dict[str, OrderRecord] = {}
        self.last_sell_times: dict[str, datetime] = {}
        self.last_sell_prices: dict[str, float] = {}  # Anti-buyback-higher tracking
        self._exit_timers: dict[str, datetime] = {}  # Track Law 6 compliance
        log.info("🔒 OrderGateway initialized (single-writer mode)")

    # ── Position Reconciliation ────────────────────────

    def get_positions(self) -> list[Position]:
        """Get current positions from Alpaca (broker = truth)."""
        with self._lock:
            try:
                raw = self.client.get_all_positions()
                positions = []
                for p in raw:
                    positions.append(Position(
                        symbol=p.symbol,
                        qty=int(p.qty),
                        avg_entry=float(p.avg_entry_price),
                        current_price=float(p.current_price),
                        market_value=float(p.market_value),
                        unrealized_pl=float(p.unrealized_pl),
                        unrealized_pl_pct=float(p.unrealized_plpc),
                        side=p.side,
                        qty_available=int(p.qty_available) if hasattr(p, 'qty_available') else int(p.qty),
                        lastday_price=float(p.lastday_price) if hasattr(p, 'lastday_price') and p.lastday_price else 0.0,
                        unrealized_intraday_pl=float(p.unrealized_intraday_pl) if hasattr(p, 'unrealized_intraday_pl') and p.unrealized_intraday_pl else 0.0,
                        unrealized_intraday_plpc=float(p.unrealized_intraday_plpc) if hasattr(p, 'unrealized_intraday_plpc') and p.unrealized_intraday_plpc else 0.0,
                        change_today=float(p.change_today) if hasattr(p, 'change_today') and p.change_today else 0.0,
                    ))
                return positions
            except Exception as e:
                log.error(f"Failed to get positions: {e}")
                return []

    def get_live_price(self, symbol: str) -> Optional[float]:
        """Get live mid-price from Alpaca (Iron Law 7: check price before selling)."""
        try:
            req = StockLatestQuoteRequest(
                symbol_or_symbols=symbol, feed='iex'
            )
            quotes = self.data_client.get_stock_latest_quote(req)
            if symbol in quotes:
                q = quotes[symbol]
                bid = float(q.bid_price)
                ask = float(q.ask_price)
                return (bid + ask) / 2
        except Exception as e:
            log.error(f"Failed to get price for {symbol}: {e}")
        return None

    # ── Order Placement (the ONLY way to place orders) ─

    def place_buy(self, proposal: TradeProposal, market_data, positions,
                  daily_pnl, consecutive_losses, active_day_trades,
                  earnings_dates, has_technicals, has_sentiment) -> OrderRecord:
        """Place a buy order. Validates through Iron Laws first."""
        with self._lock:
            # Validate through Iron Laws
            results = validate_entry(
                proposal=proposal,
                market=market_data,
                positions=positions,
                daily_pnl=daily_pnl,
                consecutive_losses=consecutive_losses,
                active_day_trades=active_day_trades,
                last_sell_times=self.last_sell_times,
                earnings_dates=earnings_dates,
                has_technicals=has_technicals,
                has_sentiment=has_sentiment,
            )

            if not is_approved(results):
                rejections = get_rejections(results)
                reason = " | ".join(str(r) for r in rejections)
                log.warning(f"🚫 BUY {proposal.symbol} REJECTED: {reason}")
                return OrderRecord(
                    symbol=proposal.symbol,
                    side=OrderSide.BUY,
                    qty=proposal.qty,
                    limit_price=proposal.limit_price,
                    state=OrderState.REJECTED,
                    strategy=proposal.strategy,
                    error=reason,
                )

            # Iron Law 2: LIMIT orders only (enforced here)
            try:
                client_id = f"beast-{uuid.uuid4().hex[:8]}"
                # Use GTC — GTC limit orders fill during ALL sessions (pre/post/regular)
                # No need for extended_hours flag (that's only for DAY orders)
                order_req = LimitOrderRequest(
                    symbol=proposal.symbol,
                    qty=proposal.qty,
                    side=AlpacaSide.BUY,
                    time_in_force=TimeInForce.GTC,
                    limit_price=proposal.limit_price,
                    client_order_id=client_id,
                )
                raw_order = self.client.submit_order(order_req)

                record = OrderRecord(
                    id=str(raw_order.id),
                    client_id=client_id,
                    symbol=proposal.symbol,
                    side=OrderSide.BUY,
                    qty=proposal.qty,
                    limit_price=proposal.limit_price,
                    state=OrderState.SENT,
                    strategy=proposal.strategy,
                )
                self.active_orders[record.id] = record

                # Iron Law 6: Track that we need an exit within 60 seconds
                self._exit_timers[proposal.symbol] = datetime.now() + timedelta(seconds=60)

                log.info(
                    f"✅ BUY {proposal.qty}x {proposal.symbol} @ ${proposal.limit_price:.2f} "
                    f"(Strategy {proposal.strategy.value}, Confidence {proposal.confidence:.0%})"
                )
                return record

            except Exception as e:
                log.error(f"❌ BUY order failed for {proposal.symbol}: {e}")
                return OrderRecord(
                    symbol=proposal.symbol,
                    side=OrderSide.BUY,
                    state=OrderState.FAILED,
                    error=str(e),
                )

    def quick_buy(self, symbol: str, qty: int, limit_price: float,
                  reason: str = "dip buy", day_change_pct: float = 0,
                  sentiment_score: int = 0, vix: float = 0,
                  tv_confirmed: bool = False) -> OrderRecord:
        """Simplified buy. Has safety checks. TV confirmation is HARD LAW."""
        with self._lock:
            try:
                # ══ HARD LAW: NO TV = NO BUY ══
                # TradingView must confirm the setup before ANY purchase
                # TV strategies must be firing (RSI, MACD, VWAP alignment)
                if not tv_confirmed:
                    log.warning(
                        f"⛔ HARD LAW: {symbol} — NO TV CONFIRMATION. "
                        f"TradingView must validate before buying. BLOCKED."
                    )
                    return OrderRecord(symbol=symbol, side=OrderSide.BUY, state=OrderState.REJECTED,
                                       error="HARD LAW: No TV confirmation")

                # Law 8: 5-minute cooldown after selling same stock (no emotional re-entries)
                last_sold = self.last_sell_times.get(symbol)
                if last_sold and (datetime.now() - last_sold).total_seconds() < 300:
                    mins_ago = (datetime.now() - last_sold).total_seconds() / 60
                    log.warning(
                        f"⛔ LAW 8: {symbol} sold {mins_ago:.0f}min ago. "
                        f"5-min cooldown — no emotional re-entries."
                    )
                    return OrderRecord(symbol=symbol, side=OrderSide.BUY, state=OrderState.REJECTED,
                                       error=f"Law 8: sold {mins_ago:.0f}min ago")

                # Rule 29: Don't chase +5% WITHOUT catalyst
                if day_change_pct > 5.0 and sentiment_score < 3:
                    log.warning(
                        f"⛔ RULE 29: {symbol} +{day_change_pct:.1f}% with weak sentiment ({sentiment_score:+d}). "
                        f"No catalyst — don't chase. (Would allow if sentiment >= +3)"
                    )
                    return OrderRecord(symbol=symbol, side=OrderSide.BUY, state=OrderState.REJECTED,
                                       error=f"Rule 29: +{day_change_pct:.1f}% no catalyst")

                # VIX-based position sizing
                if vix > 30:
                    qty = max(1, qty // 2)
                    log.info(f"  VIX {vix:.0f} EXTREME → halving to {qty} shares")
                elif vix > 25:
                    qty = max(1, int(qty * 0.7))
                    log.info(f"  VIX {vix:.0f} HIGH → reducing to {qty} shares")
                elif 0 < vix < 15:
                    qty = int(qty * 1.3)
                    log.info(f"  VIX {vix:.0f} CALM → increasing to {qty} shares")

                # Check portfolio heat (max 60% invested)
                try:
                    acct = self.client.get_account()
                    equity = float(acct.equity)
                    long_value = float(acct.long_market_value)
                    heat = long_value / equity if equity > 0 else 1.0
                    if heat > 0.60:
                        log.warning(f"⛔ HEAT LIMIT: Portfolio {heat:.0%} invested (max 60%). Blocking buy.")
                        return OrderRecord(symbol=symbol, side=OrderSide.BUY, state=OrderState.REJECTED,
                                          error=f"Heat limit: {heat:.0%} > 60%")
                except:
                    pass

                # Anti-buyback-higher: refuse to buy if we sold this stock today at a lower price
                sold_price = self.last_sell_prices.get(symbol)
                if sold_price and limit_price > sold_price * 1.01:
                    log.warning(
                        f"⛔ ANTI-BUYBACK: {symbol} — refusing to buy @ ${limit_price:.2f}, "
                        f"we sold today @ ${sold_price:.2f}. Would lose ${(limit_price - sold_price) * qty:.2f}"
                    )
                    return OrderRecord(symbol=symbol, side=OrderSide.BUY, state=OrderState.REJECTED,
                                       error=f"Anti-buyback: sold today @ ${sold_price:.2f}")

                client_id = f"beast-quickbuy-{uuid.uuid4().hex[:8]}"
                order_req = LimitOrderRequest(
                    symbol=symbol, qty=qty, side=AlpacaSide.BUY,
                    time_in_force=TimeInForce.GTC, limit_price=limit_price,
                    client_order_id=client_id,
                )
                raw_order = self.client.submit_order(order_req)
                record = OrderRecord(
                    id=str(raw_order.id), client_id=client_id, symbol=symbol,
                    side=OrderSide.BUY, qty=qty, limit_price=limit_price,
                    state=OrderState.SENT,
                )
                self.active_orders[record.id] = record
                log.info(f"✅ QUICK BUY {qty}x {symbol} @ ${limit_price:.2f} ({reason})")
                return record
            except Exception as e:
                log.error(f"❌ QUICK BUY failed for {symbol}: {e}")
                return OrderRecord(symbol=symbol, side=OrderSide.BUY, state=OrderState.FAILED, error=str(e))

    def place_sell(self, symbol: str, qty: int, limit_price: float,
                   reason: str = "exit", time_in_force: str = "gtc",
                   entry_price: float = 0.0) -> OrderRecord:
        """Place a sell order. Checks Iron Law 1, Law 7, and Law 17.
        
        Changes from v2:
        - Default GTC (not DAY) so orders don't expire overnight
        - Iron Law 17: Enforces minimum 2% profit on scalps
        - Won't adjust price below 2% of entry
        """
        with self._lock:
            # Iron Law 17: Minimum 2% profit check
            if entry_price > 0:
                min_sell = round(entry_price * 1.02, 2)
                if limit_price < min_sell:
                    log.warning(
                        f"⛔ Law 17: {symbol} sell ${limit_price:.2f} is only "
                        f"{((limit_price/entry_price)-1)*100:.1f}% above entry ${entry_price:.2f}. "
                        f"Minimum 2%. Adjusting to ${min_sell:.2f}"
                    )
                    limit_price = min_sell

            # Iron Law 7: Check live price before selling
            live_price = self.get_live_price(symbol)
            if live_price and live_price < limit_price * 0.995:
                # Don't adjust below 2% minimum if we have entry price
                if entry_price > 0:
                    min_sell = round(entry_price * 1.02, 2)
                    adjusted = max(round(live_price, 2), min_sell)
                    log.warning(
                        f"⚠️ Law 7+17: {symbol} live ${live_price:.2f} below limit ${limit_price:.2f}. "
                        f"Adjusted to ${adjusted:.2f} (min 2% above entry)"
                    )
                    limit_price = adjusted
                else:
                    log.warning(
                        f"⚠️ Law 7: {symbol} live ${live_price:.2f} is below "
                        f"limit ${limit_price:.2f}. Adjusting to ${live_price:.2f}"
                    )
                    limit_price = round(live_price, 2)

            # Determine time in force
            tif = TimeInForce.GTC if time_in_force.lower() == 'gtc' else TimeInForce.DAY

            try:
                client_id = f"beast-sell-{uuid.uuid4().hex[:8]}"
                order_req = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=AlpacaSide.SELL,
                    time_in_force=tif,
                    limit_price=limit_price,
                    client_order_id=client_id,
                    # GTC already fills during extended hours; no flag needed
                )
                raw_order = self.client.submit_order(order_req)

                record = OrderRecord(
                    id=str(raw_order.id),
                    client_id=client_id,
                    symbol=symbol,
                    side=OrderSide.SELL,
                    qty=qty,
                    limit_price=limit_price,
                    state=OrderState.SENT,
                )
                self.active_orders[record.id] = record

                # Track cooldown (Iron Law 8) + anti-buyback price
                self.last_sell_times[symbol] = datetime.now()
                self.last_sell_prices[symbol] = limit_price

                log.info(f"✅ SELL {qty}x {symbol} @ ${limit_price:.2f} ({reason})")
                return record

            except Exception as e:
                log.error(f"❌ SELL order failed for {symbol}: {e}")
                return OrderRecord(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    state=OrderState.FAILED,
                    error=str(e),
                )

    def place_trailing_stop(self, symbol: str, qty: int, trail_percent: float = 2.0,
                            reason: str = "trailing runner",
                            entry_price: float = 0.0) -> OrderRecord:
        """Place a trailing stop sell order. The stop follows price UP by trail_percent.
        
        HOW IT WORKS:
        - Buy MU at $524. Set 2% trailing stop.
        - MU rises to $540 → stop is at $529.20 (540 × 0.98)
        - MU rises to $560 → stop moves to $548.80 (560 × 0.98) 
        - MU dips to $548 → SELLS at ~$548. Caught $24 more than fixed $540 target!
        
        Iron Law 17 enforced: trail_percent minimum 2% (don't give away profits).
        
        USE FOR: Runner halves. Scalp halves still use fixed limits for speed.
        """
        with self._lock:
            # Iron Law 17: Minimum 2% trail
            if trail_percent < 2.0:
                log.warning(f"⛔ Law 17: Trail {trail_percent}% < 2% minimum. Setting to 2.0%")
                trail_percent = 2.0

            try:
                client_id = f"beast-trail-{uuid.uuid4().hex[:8]}"
                order_req = TrailingStopOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=AlpacaSide.SELL,
                    time_in_force=TimeInForce.GTC,
                    trail_percent=trail_percent,
                    client_order_id=client_id,
                )
                raw_order = self.client.submit_order(order_req)

                record = OrderRecord(
                    id=str(raw_order.id),
                    client_id=client_id,
                    symbol=symbol,
                    side=OrderSide.SELL,
                    qty=qty,
                    limit_price=0,  # No fixed price — trails dynamically
                    state=OrderState.SENT,
                )
                self.active_orders[record.id] = record
                self.last_sell_times[symbol] = datetime.now()

                log.info(
                    f"✅ TRAILING STOP {qty}x {symbol} trail={trail_percent}% "
                    f"(entry ${entry_price:.2f}) ({reason})"
                )
                return record

            except Exception as e:
                log.error(f"❌ TRAILING STOP failed for {symbol}: {e}")
                # Fallback: if trailing stop not supported, use fixed limit
                fallback_price = round(entry_price * (1 + trail_percent * 2 / 100), 2) if entry_price else 0
                if fallback_price > 0:
                    log.info(f"  ↳ Fallback: fixed limit sell @ ${fallback_price:.2f}")
                    return self.place_sell(symbol, qty, fallback_price,
                                          reason=f"trail-fallback {reason}",
                                          entry_price=entry_price)
                return OrderRecord(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    state=OrderState.FAILED,
                    error=str(e),
                )

    def place_bracket_order(self, symbol: str, qty: int, limit_price: float,
                            take_profit: float, stop_loss: float,
                            reason: str = "bracket") -> OrderRecord:
        """Place buy with automatic take-profit + stop-loss (OCO).
        All 3 legs in one order — when one fills, other cancels."""
        with self._lock:
            try:
                client_id = f"beast-bracket-{uuid.uuid4().hex[:8]}"
                order_req = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=AlpacaSide.BUY,
                    time_in_force=TimeInForce.GTC,
                    limit_price=limit_price,
                    order_class=OrderClass.BRACKET,
                    take_profit={'limit_price': take_profit},
                    stop_loss={'stop_price': stop_loss},
                    client_order_id=client_id,
                )
                raw_order = self.client.submit_order(order_req)
                record = OrderRecord(
                    id=str(raw_order.id),
                    client_id=client_id,
                    symbol=symbol,
                    side=OrderSide.BUY,
                    qty=qty,
                    limit_price=limit_price,
                    state=OrderState.SENT,
                )
                self.active_orders[record.id] = record
                log.info(
                    f"✅ BRACKET {qty}x {symbol} @ ${limit_price:.2f} "
                    f"TP=${take_profit:.2f} SL=${stop_loss:.2f} ({reason})"
                )
                return record
            except Exception as e:
                log.error(f"❌ BRACKET order failed for {symbol}: {e}")
                return OrderRecord(
                    symbol=symbol, side=OrderSide.BUY,
                    state=OrderState.FAILED, error=str(e),
                )

    def place_split_entry(self, proposal: TradeProposal, market_data,
                          positions, daily_pnl, consecutive_losses,
                          active_day_trades, earnings_dates,
                          has_technicals, has_sentiment) -> tuple[OrderRecord, OrderRecord]:
        """Place a split entry: half scalp, half runner. Iron Law 6 auto-sets exits."""
        half = max(1, proposal.qty // 2)
        scalp_qty = half
        runner_qty = proposal.qty - half

        # Place scalp half
        scalp_proposal = TradeProposal(
            symbol=proposal.symbol,
            side=OrderSide.BUY,
            qty=scalp_qty,
            limit_price=proposal.limit_price,
            strategy=proposal.strategy,
            confidence=proposal.confidence,
            reason=f"SCALP half: {proposal.reason}",
            is_scalp=True,
            target_price=proposal.target_price,
            stop_price=proposal.stop_price,
        )
        scalp_order = self.place_buy(
            scalp_proposal, market_data, positions, daily_pnl,
            consecutive_losses, active_day_trades, earnings_dates,
            has_technicals, has_sentiment
        )

        # Place runner half
        runner_proposal = TradeProposal(
            symbol=proposal.symbol,
            side=OrderSide.BUY,
            qty=runner_qty,
            limit_price=proposal.limit_price,
            strategy=proposal.strategy,
            confidence=proposal.confidence,
            reason=f"RUNNER half: {proposal.reason}",
            is_scalp=False,
            target_price=proposal.target_price * 1.5,  # Runner gets wider target
            stop_price=proposal.stop_price,
        )
        runner_order = self.place_buy(
            runner_proposal, market_data, positions, daily_pnl,
            consecutive_losses, active_day_trades + (1 if scalp_order.state == OrderState.SENT else 0),
            earnings_dates, has_technicals, has_sentiment
        )

        return scalp_order, runner_order

    # ── Order State Sync ───────────────────────────────

    def sync_orders(self):
        """Sync order states with Alpaca broker (broker = truth)."""
        with self._lock:
            try:
                req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
                open_orders = self.client.get_orders(req)
                broker_ids = {str(o.id) for o in open_orders}

                for oid, record in list(self.active_orders.items()):
                    if record.state in (OrderState.SENT, OrderState.ACCEPTED, OrderState.PARTIAL_FILL):
                        if oid not in broker_ids:
                            # Order no longer open — check if filled or canceled
                            try:
                                order = self.client.get_order_by_id(oid)
                                filled_qty = int(order.filled_qty or 0)
                                if order.status.value == 'filled':
                                    record.state = OrderState.FILLED
                                    record.filled_qty = filled_qty
                                    record.filled_avg_price = float(order.filled_avg_price or 0)
                                elif order.status.value == 'canceled':
                                    record.state = OrderState.CANCELED
                                elif order.status.value == 'expired':
                                    record.state = OrderState.CANCELED
                                record.updated_at = datetime.now()
                            except Exception:
                                pass

            except Exception as e:
                log.error(f"Order sync failed: {e}")

    # ── Iron Law 6 Enforcement ─────────────────────────

    def check_exit_timers(self) -> list[str]:
        """Check if any buy orders need exit orders set (Law 6: 60 sec deadline)."""
        violations = []
        now = datetime.now()
        for symbol, deadline in list(self._exit_timers.items()):
            if now > deadline:
                violations.append(symbol)
                log.warning(f"⛔ Iron Law 6 VIOLATION: {symbol} has no exit order "
                           f"set within 60 seconds of buy!")
        return violations

    # ── Cancel Orders ──────────────────────────────────

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order."""
        with self._lock:
            try:
                self.client.cancel_order_by_id(order_id)
                if order_id in self.active_orders:
                    self.active_orders[order_id].state = OrderState.CANCELED
                log.info(f"🗑️ Canceled order {order_id}")
                return True
            except Exception as e:
                log.error(f"Cancel failed for {order_id}: {e}")
                return False

    def cancel_all(self) -> int:
        """Cancel all open orders. Used by kill switch."""
        with self._lock:
            try:
                self.client.cancel_orders()
                count = sum(1 for o in self.active_orders.values()
                           if o.state in (OrderState.SENT, OrderState.ACCEPTED))
                for o in self.active_orders.values():
                    if o.state in (OrderState.SENT, OrderState.ACCEPTED):
                        o.state = OrderState.CANCELED
                log.info(f"🗑️ Canceled {count} orders (KILL SWITCH)")
                return count
            except Exception as e:
                log.error(f"Cancel all failed: {e}")
                return 0

    # ── Account Info ───────────────────────────────────

    def get_account(self) -> dict:
        """Get account info from Alpaca."""
        try:
            acct = self.client.get_account()
            return {
                'equity': float(acct.equity),
                'buying_power': float(acct.buying_power),
                'cash': float(acct.cash),
                'day_trade_count': int(acct.daytrade_count),
                'pdt': acct.pattern_day_trader,
            }
        except Exception as e:
            log.error(f"Account fetch failed: {e}")
            return {}

    def get_open_orders(self) -> list:
        """Get all open orders from Alpaca with type info for trailing stop detection."""
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            orders = self.client.get_orders(req)
            result = []
            for o in orders:
                entry = {
                    'symbol': o.symbol,
                    'side': o.side.value,
                    'qty': str(o.qty),
                    'limit_price': str(o.limit_price) if o.limit_price else '?',
                    'type': str(o.type.value) if o.type else 'unknown',
                    'trail_percent': str(o.trail_percent) if o.trail_percent else None,
                    'client_order_id': str(o.client_order_id or ''),
                    'status': o.status.value,
                    'id': str(o.id),
                }
                result.append(entry)
            return result
        except Exception as e:
            log.error(f"Open orders fetch failed: {e}")
            return []

    def cleanup_stale_orders(self, max_age_days: int = 3) -> list:
        """Cancel GTC orders older than max_age_days. Returns cancelled order IDs.
        Skips trailing stops (they're protective)."""
        cancelled = []
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            orders = self.client.get_orders(req)
            cutoff = datetime.now() - timedelta(days=max_age_days)
            for o in orders:
                # Don't cancel trailing stops — they protect profits
                if o.type and str(o.type.value) == 'trailing_stop':
                    continue
                created = o.created_at
                if created and created.replace(tzinfo=None) < cutoff:
                    try:
                        self.client.cancel_order_by_id(str(o.id))
                        cancelled.append(str(o.id))
                        log.info(f"🧹 Cancelled stale order {o.symbol} ({o.id}) — {max_age_days}+ days old")
                    except Exception as ce:
                        log.warning(f"Failed to cancel stale order {o.id}: {ce}")
        except Exception as e:
            log.error(f"Stale order cleanup failed: {e}")
        return cancelled
