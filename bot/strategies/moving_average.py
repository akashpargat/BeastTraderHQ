"""Moving Average Crossover strategy.

Generates a BUY signal when the fast EMA crosses above the slow EMA, and a
SELL signal when it crosses below.  Otherwise emits HOLD.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import BaseStrategy, Signal


class MovingAverageCrossoverStrategy(BaseStrategy):
    """Dual exponential moving-average (EMA) crossover strategy.

    Parameters (passed via *params* dict)
    --------------------------------------
    fast_period : int
        EMA period for the fast (short) line.  Default: 9.
    slow_period : int
        EMA period for the slow (long) line.  Default: 21.
    """

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        super().__init__(params)
        self.fast_period: int = int(self.params.get("fast_period", 9))
        self.slow_period: int = int(self.params.get("slow_period", 21))
        if self.fast_period >= self.slow_period:
            raise ValueError(
                f"fast_period ({self.fast_period}) must be less than "
                f"slow_period ({self.slow_period})."
            )

    def generate_signal(self, candles: pd.DataFrame) -> Signal:
        """Return BUY / SELL / HOLD based on EMA crossover."""
        self._validate_candles(candles, self.slow_period + 1)

        close = candles["close"].astype(float)
        fast_ema = close.ewm(span=self.fast_period, adjust=False).mean()
        slow_ema = close.ewm(span=self.slow_period, adjust=False).mean()

        # Current and previous bar values
        fast_now, fast_prev = fast_ema.iloc[-1], fast_ema.iloc[-2]
        slow_now, slow_prev = slow_ema.iloc[-1], slow_ema.iloc[-2]
        current_price = float(close.iloc[-1])

        metadata = {
            "fast_ema": round(fast_now, 6),
            "slow_ema": round(slow_now, 6),
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
        }

        # Golden cross: fast crosses above slow
        if fast_prev <= slow_prev and fast_now > slow_now:
            return Signal(Signal.BUY, current_price, metadata)
        # Death cross: fast crosses below slow
        if fast_prev >= slow_prev and fast_now < slow_now:
            return Signal(Signal.SELL, current_price, metadata)
        return Signal(Signal.HOLD, current_price, metadata)
