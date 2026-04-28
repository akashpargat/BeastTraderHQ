"""Relative Strength Index (RSI) strategy.

Generates a BUY signal when the RSI crosses up through the oversold level,
a SELL signal when it crosses down through the overbought level, and HOLD
otherwise.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import BaseStrategy, Signal


class RSIStrategy(BaseStrategy):
    """RSI mean-reversion strategy.

    Parameters (passed via *params* dict)
    --------------------------------------
    rsi_period : int
        Lookback period for the RSI calculation.  Default: 14.
    rsi_overbought : float
        RSI level above which the asset is considered overbought.  Default: 70.
    rsi_oversold : float
        RSI level below which the asset is considered oversold.  Default: 30.
    """

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        super().__init__(params)
        self.rsi_period: int = int(self.params.get("rsi_period", 14))
        self.rsi_overbought: float = float(self.params.get("rsi_overbought", 70))
        self.rsi_oversold: float = float(self.params.get("rsi_oversold", 30))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_rsi(self, close: pd.Series) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=self.rsi_period - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=self.rsi_period - 1, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))
        return rsi

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate_signal(self, candles: pd.DataFrame) -> Signal:
        """Return BUY / SELL / HOLD based on RSI levels."""
        self._validate_candles(candles, self.rsi_period + 1)

        close = candles["close"].astype(float)
        rsi = self._compute_rsi(close)

        rsi_now = rsi.iloc[-1]
        rsi_prev = rsi.iloc[-2]
        current_price = float(close.iloc[-1])

        metadata = {
            "rsi": round(rsi_now, 4),
            "rsi_period": self.rsi_period,
            "rsi_overbought": self.rsi_overbought,
            "rsi_oversold": self.rsi_oversold,
        }

        # RSI crosses up through oversold → BUY
        if rsi_prev <= self.rsi_oversold < rsi_now:
            return Signal(Signal.BUY, current_price, metadata)
        # RSI crosses down through overbought → SELL
        if rsi_prev >= self.rsi_overbought > rsi_now:
            return Signal(Signal.SELL, current_price, metadata)
        return Signal(Signal.HOLD, current_price, metadata)
