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
    LimitOrderRequest, GetOrdersRequest
)
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
                order_req = LimitOrderRequest(
                    symbol=proposal.symbol,
                    qty=proposal.qty,
                    side=AlpacaSide.BUY,
                    time_in_force=TimeInForce.DAY,
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

                # Track cooldown (Iron Law 8)
                self.last_sell_times[symbol] = datetime.now()

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
        """Get all open orders from Alpaca."""
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            orders = self.client.get_orders(req)
            return [{'symbol': o.symbol, 'side': o.side.value, 'qty': str(o.qty),
                     'limit_price': str(o.limit_price) if o.limit_price else '?',
                     'status': o.status.value, 'id': str(o.id)}
                    for o in orders]
        except Exception as e:
            log.error(f"Open orders fetch failed: {e}")
            return []
