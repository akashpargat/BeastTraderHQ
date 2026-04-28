"""Exchange client wrapper built on top of CCXT."""

from __future__ import annotations

import logging
from typing import Any

import ccxt
import pandas as pd


class ExchangeClient:
    """Thin wrapper around a CCXT exchange instance.

    Parameters
    ----------
    exchange_id:
        CCXT exchange identifier (e.g. ``"binance"``).
    api_key:
        Exchange API key.
    api_secret:
        Exchange API secret.
    sandbox:
        When *True*, enable the exchange's sandbox / paper-trading mode.
    logger:
        Optional :class:`logging.Logger`.  A default logger is used if *None*.
    """

    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        sandbox: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        self._log = logger or logging.getLogger(__name__)

        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Unsupported exchange: {exchange_id!r}")

        self._exchange: ccxt.Exchange = exchange_class(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            }
        )

        if sandbox:
            if self._exchange.has.get("sandbox"):
                self._exchange.set_sandbox_mode(True)
                self._log.info("Sandbox mode enabled for %s", exchange_id)
            else:
                self._log.warning(
                    "%s does not support sandbox mode – running against live API.",
                    exchange_id,
                )

        self._log.info("Exchange client initialised: %s", exchange_id)

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> pd.DataFrame:
        """Fetch OHLCV candles and return them as a DataFrame.

        Parameters
        ----------
        symbol:
            Trading pair, e.g. ``"BTC/USDT"``.
        timeframe:
            Candle timeframe string, e.g. ``"1h"``, ``"15m"``.
        limit:
            Number of candles to fetch.

        Returns
        -------
        pandas.DataFrame
            Columns: ``timestamp``, ``open``, ``high``, ``low``, ``close``, ``volume``.
        """
        raw = self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """Return the latest ticker data for *symbol*."""
        return self._exchange.fetch_ticker(symbol)

    def fetch_balance(self) -> dict[str, Any]:
        """Return account balance information."""
        return self._exchange.fetch_balance()

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def place_market_buy(self, symbol: str, amount: float) -> dict[str, Any]:
        """Place a market buy order.

        Parameters
        ----------
        symbol:
            Trading pair, e.g. ``"BTC/USDT"``.
        amount:
            Amount of base currency to buy.

        Returns
        -------
        dict
            Raw CCXT order response.
        """
        self._log.info("Placing market BUY  %s  amount=%s", symbol, amount)
        order = self._exchange.create_market_buy_order(symbol, amount)
        self._log.info("Order placed: %s", order.get("id"))
        return order

    def place_market_sell(self, symbol: str, amount: float) -> dict[str, Any]:
        """Place a market sell order.

        Parameters
        ----------
        symbol:
            Trading pair, e.g. ``"BTC/USDT"``.
        amount:
            Amount of base currency to sell.

        Returns
        -------
        dict
            Raw CCXT order response.
        """
        self._log.info("Placing market SELL  %s  amount=%s", symbol, amount)
        order = self._exchange.create_market_sell_order(symbol, amount)
        self._log.info("Order placed: %s", order.get("id"))
        return order

    def fetch_open_orders(self, symbol: str) -> list[dict[str, Any]]:
        """Return all open orders for *symbol*."""
        return self._exchange.fetch_open_orders(symbol)

    def cancel_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        """Cancel an order by its ID."""
        self._log.info("Cancelling order %s on %s", order_id, symbol)
        return self._exchange.cancel_order(order_id, symbol)
