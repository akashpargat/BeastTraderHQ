"""Abstract base class for trading strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class Signal:
    """Represents a trade signal emitted by a strategy.

    Attributes
    ----------
    action:
        ``"buy"``, ``"sell"``, or ``"hold"``.
    price:
        The price at which the signal was generated.
    metadata:
        Optional dictionary with extra information (e.g., indicator values).
    """

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

    def __init__(self, action: str, price: float, metadata: dict[str, Any] | None = None) -> None:
        if action not in (self.BUY, self.SELL, self.HOLD):
            raise ValueError(f"Invalid signal action: {action!r}")
        self.action = action
        self.price = price
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        return f"Signal(action={self.action!r}, price={self.price})"


class BaseStrategy(ABC):
    """All trading strategies must subclass this and implement :meth:`generate_signal`.

    Parameters
    ----------
    params:
        Strategy-specific hyper-parameters passed from the configuration file.
    """

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params: dict[str, Any] = params or {}

    @abstractmethod
    def generate_signal(self, candles: pd.DataFrame) -> Signal:
        """Analyse OHLCV candle data and return a :class:`Signal`.

        Parameters
        ----------
        candles:
            A :class:`~pandas.DataFrame` with columns
            ``["timestamp", "open", "high", "low", "close", "volume"]``
            sorted in ascending order (oldest first).
        """

    def _validate_candles(self, candles: pd.DataFrame, min_rows: int) -> None:
        """Raise ValueError if *candles* does not have enough rows."""
        if len(candles) < min_rows:
            raise ValueError(
                f"{self.__class__.__name__} requires at least {min_rows} candles, "
                f"but only {len(candles)} were provided."
            )
