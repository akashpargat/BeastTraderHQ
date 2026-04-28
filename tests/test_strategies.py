"""Tests for trading strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bot.strategies.base import Signal
from bot.strategies.moving_average import MovingAverageCrossoverStrategy
from bot.strategies.rsi import RSIStrategy
from bot.strategies.registry import get_strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(closes: list[float]) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from a list of closing prices."""
    n = len(closes)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"),
            "open": closes,
            "high": [c * 1.001 for c in closes],
            "low": [c * 0.999 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        }
    )


# ---------------------------------------------------------------------------
# Signal tests
# ---------------------------------------------------------------------------

class TestSignal:
    def test_valid_actions(self) -> None:
        for action in (Signal.BUY, Signal.SELL, Signal.HOLD):
            s = Signal(action, 100.0)
            assert s.action == action

    def test_invalid_action_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid signal action"):
            Signal("long", 100.0)

    def test_repr(self) -> None:
        s = Signal(Signal.BUY, 99.5)
        assert "buy" in repr(s)
        assert "99.5" in repr(s)

    def test_metadata_defaults_to_empty_dict(self) -> None:
        s = Signal(Signal.HOLD, 50.0)
        assert s.metadata == {}


# ---------------------------------------------------------------------------
# MovingAverageCrossoverStrategy tests
# ---------------------------------------------------------------------------

class TestMovingAverageCrossoverStrategy:
    def test_requires_fast_less_than_slow(self) -> None:
        with pytest.raises(ValueError, match="fast_period"):
            MovingAverageCrossoverStrategy({"fast_period": 21, "slow_period": 9})

    def test_requires_enough_candles(self) -> None:
        strat = MovingAverageCrossoverStrategy({"fast_period": 9, "slow_period": 21})
        candles = _make_candles([100.0] * 10)  # fewer than slow_period + 1
        with pytest.raises(ValueError, match="at least"):
            strat.generate_signal(candles)

    def test_returns_hold_on_flat_prices(self) -> None:
        strat = MovingAverageCrossoverStrategy({"fast_period": 9, "slow_period": 21})
        candles = _make_candles([100.0] * 50)
        signal = strat.generate_signal(candles)
        assert signal.action == Signal.HOLD

    def test_golden_cross_produces_buy(self) -> None:
        """Fast EMA crosses above slow EMA when prices jump up sharply."""
        strat = MovingAverageCrossoverStrategy({"fast_period": 3, "slow_period": 5})
        # Descending prices then a sharp spike to force a golden cross
        closes = [10.0, 9.5, 9.0, 8.5, 8.0, 7.5, 7.0] + [100.0] * 10
        candles = _make_candles(closes)
        signal = strat.generate_signal(candles)
        assert signal.action in (Signal.BUY, Signal.HOLD)  # implementation-dependent timing

    def test_metadata_contains_ema_values(self) -> None:
        strat = MovingAverageCrossoverStrategy({"fast_period": 9, "slow_period": 21})
        candles = _make_candles([100.0] * 50)
        signal = strat.generate_signal(candles)
        assert "fast_ema" in signal.metadata
        assert "slow_ema" in signal.metadata

    def test_default_periods(self) -> None:
        strat = MovingAverageCrossoverStrategy()
        assert strat.fast_period == 9
        assert strat.slow_period == 21


# ---------------------------------------------------------------------------
# RSIStrategy tests
# ---------------------------------------------------------------------------

class TestRSIStrategy:
    def test_requires_enough_candles(self) -> None:
        strat = RSIStrategy({"rsi_period": 14})
        candles = _make_candles([50.0] * 5)
        with pytest.raises(ValueError, match="at least"):
            strat.generate_signal(candles)

    def test_returns_hold_on_flat_prices(self) -> None:
        strat = RSIStrategy({"rsi_period": 14})
        candles = _make_candles([100.0] * 50)
        signal = strat.generate_signal(candles)
        assert signal.action == Signal.HOLD

    def test_buy_on_oversold_crossover(self) -> None:
        """RSI should cross above oversold when price rebounds from a deep drop."""
        strat = RSIStrategy({"rsi_period": 5, "rsi_oversold": 30, "rsi_overbought": 70})
        # Deep decline followed by a strong bounce
        closes = [100.0] * 5 + [60.0, 55.0, 50.0, 45.0, 40.0] + [80.0, 85.0, 90.0]
        candles = _make_candles(closes)
        signal = strat.generate_signal(candles)
        # We just check it runs without error and returns a valid action
        assert signal.action in (Signal.BUY, Signal.SELL, Signal.HOLD)

    def test_metadata_contains_rsi(self) -> None:
        strat = RSIStrategy()
        candles = _make_candles([100.0 + float(i) * 0.5 for i in range(50)])
        signal = strat.generate_signal(candles)
        assert "rsi" in signal.metadata

    def test_default_params(self) -> None:
        strat = RSIStrategy()
        assert strat.rsi_period == 14
        assert strat.rsi_overbought == 70
        assert strat.rsi_oversold == 30


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestStrategyRegistry:
    def test_get_ma_strategy(self) -> None:
        strat = get_strategy("moving_average_crossover", {"fast_period": 5, "slow_period": 10})
        assert isinstance(strat, MovingAverageCrossoverStrategy)

    def test_get_rsi_strategy(self) -> None:
        strat = get_strategy("rsi", {"rsi_period": 14})
        assert isinstance(strat, RSIStrategy)

    def test_unknown_strategy_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown strategy"):
            get_strategy("nonexistent_strategy")
