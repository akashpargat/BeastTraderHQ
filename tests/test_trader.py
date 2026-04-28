"""Tests for the BeastTrader orchestrator."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from bot.config import Config
from bot.strategies.base import Signal
from bot.trader import BeastTrader


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CONFIG_CONTENT = """
    exchange:
      id: binance
      api_key: "test_key"
      api_secret: "test_secret"
      sandbox: true
    trading:
      symbol: "BTC/USDT"
      trade_amount: 100.0
      max_open_positions: 2
    strategy:
      name: moving_average_crossover
      params:
        fast_period: 9
        slow_period: 21
    timeframe: "1h"
    candle_limit: 50
"""


@pytest.fixture()
def config(tmp_path: Path) -> Config:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(textwrap.dedent(VALID_CONFIG_CONTENT))
    return Config(cfg_file)


@pytest.fixture()
def mock_exchange() -> MagicMock:
    exchange = MagicMock()
    # Default: return a minimal OHLCV dataframe (22 rows for MA crossover)
    closes = [100.0 + float(i) for i in range(22)]
    exchange.fetch_ohlcv.return_value = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=22, freq="1h", tz="UTC"),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1000.0] * 22,
        }
    )
    exchange.place_market_buy.return_value = {"id": "order-buy-1"}
    exchange.place_market_sell.return_value = {"id": "order-sell-1"}
    return exchange


@pytest.fixture()
def trader(config: Config, mock_exchange: MagicMock) -> BeastTrader:
    return BeastTrader(config, exchange_client=mock_exchange)


# ---------------------------------------------------------------------------
# BeastTrader tests
# ---------------------------------------------------------------------------

class TestBeastTrader:
    def test_initialises_without_error(self, config: Config, mock_exchange: MagicMock) -> None:
        t = BeastTrader(config, exchange_client=mock_exchange)
        assert t is not None

    def test_run_once_returns_signal(self, trader: BeastTrader) -> None:
        signal = trader.run_once()
        assert isinstance(signal, Signal)
        assert signal.action in (Signal.BUY, Signal.SELL, Signal.HOLD)

    def test_run_once_fetches_ohlcv(self, trader: BeastTrader, mock_exchange: MagicMock) -> None:
        trader.run_once()
        mock_exchange.fetch_ohlcv.assert_called_once_with(
            "BTC/USDT", timeframe="1h", limit=50
        )

    def test_buy_signal_places_order(self, config: Config, mock_exchange: MagicMock) -> None:
        trader = BeastTrader(config, exchange_client=mock_exchange)
        buy_signal = Signal(Signal.BUY, 50000.0)
        trader._handle_signal(buy_signal)
        mock_exchange.place_market_buy.assert_called_once()

    def test_sell_signal_with_no_positions_does_not_sell(
        self, config: Config, mock_exchange: MagicMock
    ) -> None:
        trader = BeastTrader(config, exchange_client=mock_exchange)
        sell_signal = Signal(Signal.SELL, 50000.0)
        trader._handle_signal(sell_signal)
        mock_exchange.place_market_sell.assert_not_called()

    def test_sell_signal_closes_open_position(
        self, config: Config, mock_exchange: MagicMock
    ) -> None:
        trader = BeastTrader(config, exchange_client=mock_exchange)
        # Manually open a position
        trader._open_positions = [
            {"order_id": "buy-1", "symbol": "BTC/USDT", "amount": 0.002, "entry_price": 49000.0}
        ]
        sell_signal = Signal(Signal.SELL, 51000.0)
        trader._handle_signal(sell_signal)
        mock_exchange.place_market_sell.assert_called_once()
        assert len(trader._open_positions) == 0

    def test_max_open_positions_respected(
        self, config: Config, mock_exchange: MagicMock
    ) -> None:
        trader = BeastTrader(config, exchange_client=mock_exchange)
        # Fill up to max
        trader._open_positions = [
            {"order_id": "buy-1", "symbol": "BTC/USDT", "amount": 0.001, "entry_price": 48000.0},
            {"order_id": "buy-2", "symbol": "BTC/USDT", "amount": 0.001, "entry_price": 49000.0},
        ]
        buy_signal = Signal(Signal.BUY, 50000.0)
        trader._handle_signal(buy_signal)
        # No new buy should be placed since max_open_positions == 2
        mock_exchange.place_market_buy.assert_not_called()

    def test_hold_signal_does_nothing(
        self, config: Config, mock_exchange: MagicMock
    ) -> None:
        trader = BeastTrader(config, exchange_client=mock_exchange)
        hold_signal = Signal(Signal.HOLD, 50000.0)
        trader._handle_signal(hold_signal)
        mock_exchange.place_market_buy.assert_not_called()
        mock_exchange.place_market_sell.assert_not_called()
