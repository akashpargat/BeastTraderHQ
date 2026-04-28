"""Core trading bot orchestrator."""

from __future__ import annotations

import time
import logging
from typing import Any

from .config import Config
from .logger import get_logger
from .exchange.client import ExchangeClient
from .strategies.base import Signal
from .strategies.registry import get_strategy


class BeastTrader:
    """Main trading bot that wires together config, exchange, and strategy.

    Parameters
    ----------
    config:
        A loaded :class:`~bot.config.Config` instance.
    exchange_client:
        Optional pre-built :class:`~bot.exchange.client.ExchangeClient`.
        Useful for testing (inject a mock).  If *None*, one is constructed
        from *config*.
    """

    def __init__(
        self,
        config: Config,
        exchange_client: ExchangeClient | None = None,
    ) -> None:
        self._config = config
        self._log: logging.Logger = get_logger(
            "beast_trader",
            level=config.log_level,
            log_file=config.log_file,
        )
        self._exchange = exchange_client or ExchangeClient(
            exchange_id=config.exchange_id,
            api_key=config.api_key,
            api_secret=config.api_secret,
            sandbox=config.sandbox,
            logger=self._log,
        )
        self._strategy = get_strategy(config.strategy_name, config.strategy_params)
        self._open_positions: list[dict[str, Any]] = []
        self._log.info(
            "BeastTrader initialised  symbol=%s  strategy=%s  timeframe=%s",
            config.symbol,
            config.strategy_name,
            config.timeframe,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run_once(self) -> Signal:
        """Execute one trading cycle: fetch candles → evaluate → act.

        Returns
        -------
        Signal
            The signal that was evaluated in this cycle.
        """
        candles = self._exchange.fetch_ohlcv(
            self._config.symbol,
            timeframe=self._config.timeframe,
            limit=self._config.candle_limit,
        )
        signal = self._strategy.generate_signal(candles)
        self._log.info("Signal: %s", signal)
        self._handle_signal(signal)
        return signal

    def run(self, interval_seconds: int = 60) -> None:
        """Run the bot in a continuous loop with *interval_seconds* between cycles.

        Press Ctrl-C to stop.
        """
        self._log.info("Starting BeastTrader loop (interval=%ds) …", interval_seconds)
        try:
            while True:
                try:
                    self.run_once()
                except Exception as exc:  # noqa: BLE001
                    self._log.error("Error during trading cycle: %s", exc, exc_info=True)
                self._log.debug("Sleeping %d seconds …", interval_seconds)
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            self._log.info("BeastTrader stopped by user.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_signal(self, signal: Signal) -> None:
        """Act on a signal by placing orders when appropriate."""
        if signal.action == Signal.BUY:
            self._open_position(signal)
        elif signal.action == Signal.SELL:
            self._close_position(signal)
        # HOLD – do nothing

    def _open_position(self, signal: Signal) -> None:
        """Open a new long position if capacity allows."""
        if len(self._open_positions) >= self._config.max_open_positions:
            self._log.info(
                "Max open positions (%d) reached – skipping BUY.",
                self._config.max_open_positions,
            )
            return

        amount = self._config.trade_amount / signal.price
        order = self._exchange.place_market_buy(self._config.symbol, amount)
        self._open_positions.append(
            {
                "order_id": order.get("id"),
                "symbol": self._config.symbol,
                "amount": amount,
                "entry_price": signal.price,
            }
        )
        self._log.info(
            "Position opened  order_id=%s  amount=%.6f  entry_price=%s",
            order.get("id"),
            amount,
            signal.price,
        )

    def _close_position(self, signal: Signal) -> None:
        """Close all open long positions."""
        if not self._open_positions:
            self._log.info("No open positions to close.")
            return

        for position in list(self._open_positions):
            order = self._exchange.place_market_sell(
                self._config.symbol, position["amount"]
            )
            pnl = (signal.price - position["entry_price"]) * position["amount"]
            self._log.info(
                "Position closed  order_id=%s  pnl=%.4f  exit_price=%s",
                order.get("id"),
                pnl,
                signal.price,
            )
            self._open_positions.remove(position)
