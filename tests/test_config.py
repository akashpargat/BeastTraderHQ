"""Tests for bot.config."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from bot.config import Config, ConfigError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_config(tmp_path: Path, content: str) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(textwrap.dedent(content))
    return cfg


VALID_CONFIG = """
    exchange:
      id: binance
      api_key: "test_key"
      api_secret: "test_secret"
      sandbox: true
    trading:
      symbol: "BTC/USDT"
      trade_amount: 50.0
      max_open_positions: 3
      risk_per_trade: 0.01
    strategy:
      name: moving_average_crossover
      params:
        fast_period: 9
        slow_period: 21
    timeframe: "1h"
    candle_limit: 100
    logging:
      level: INFO
      file: "logs/test.log"
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConfigLoading:
    def test_loads_valid_config(self, tmp_path: Path) -> None:
        cfg = Config(_write_config(tmp_path, VALID_CONFIG))
        assert cfg.exchange_id == "binance"
        assert cfg.api_key == "test_key"
        assert cfg.api_secret == "test_secret"
        assert cfg.sandbox is True

    def test_trading_fields(self, tmp_path: Path) -> None:
        cfg = Config(_write_config(tmp_path, VALID_CONFIG))
        assert cfg.symbol == "BTC/USDT"
        assert cfg.trade_amount == 50.0
        assert cfg.max_open_positions == 3
        assert cfg.risk_per_trade == 0.01

    def test_strategy_fields(self, tmp_path: Path) -> None:
        cfg = Config(_write_config(tmp_path, VALID_CONFIG))
        assert cfg.strategy_name == "moving_average_crossover"
        assert cfg.strategy_params == {"fast_period": 9, "slow_period": 21}

    def test_timeframe_and_limit(self, tmp_path: Path) -> None:
        cfg = Config(_write_config(tmp_path, VALID_CONFIG))
        assert cfg.timeframe == "1h"
        assert cfg.candle_limit == 100

    def test_logging_fields(self, tmp_path: Path) -> None:
        cfg = Config(_write_config(tmp_path, VALID_CONFIG))
        assert cfg.log_level == "INFO"
        assert cfg.log_file == "logs/test.log"


class TestConfigDefaults:
    def test_sandbox_defaults_to_false(self, tmp_path: Path) -> None:
        content = VALID_CONFIG.replace("sandbox: true", "")
        cfg = Config(_write_config(tmp_path, content))
        assert cfg.sandbox is False

    def test_max_open_positions_default(self, tmp_path: Path) -> None:
        content = VALID_CONFIG.replace("max_open_positions: 3", "")
        cfg = Config(_write_config(tmp_path, content))
        assert cfg.max_open_positions == 1

    def test_risk_per_trade_default(self, tmp_path: Path) -> None:
        content = VALID_CONFIG.replace("risk_per_trade: 0.01", "")
        cfg = Config(_write_config(tmp_path, content))
        assert cfg.risk_per_trade == 0.01

    def test_candle_limit_default(self, tmp_path: Path) -> None:
        content = VALID_CONFIG.replace("candle_limit: 100", "")
        cfg = Config(_write_config(tmp_path, content))
        assert cfg.candle_limit == 100


class TestConfigErrors:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            Config(tmp_path / "nonexistent.yaml")

    def test_missing_exchange_section_raises(self, tmp_path: Path) -> None:
        content = """
            trading:
              symbol: "BTC/USDT"
              trade_amount: 50.0
            strategy:
              name: rsi
        """
        with pytest.raises(ConfigError, match="exchange"):
            Config(_write_config(tmp_path, content))

    def test_missing_trading_section_raises(self, tmp_path: Path) -> None:
        content = """
            exchange:
              id: binance
              api_key: key
              api_secret: secret
            strategy:
              name: rsi
        """
        with pytest.raises(ConfigError, match="trading"):
            Config(_write_config(tmp_path, content))

    def test_missing_strategy_section_raises(self, tmp_path: Path) -> None:
        content = """
            exchange:
              id: binance
              api_key: key
              api_secret: secret
            trading:
              symbol: "BTC/USDT"
              trade_amount: 50.0
        """
        with pytest.raises(ConfigError, match="strategy"):
            Config(_write_config(tmp_path, content))

    def test_empty_api_key_raises(self, tmp_path: Path) -> None:
        content = VALID_CONFIG.replace("api_key: \"test_key\"", "api_key: \"\"")
        with pytest.raises(ConfigError, match="api_key"):
            Config(_write_config(tmp_path, content))
