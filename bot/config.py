"""Configuration loader for BeastTraderHQ."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


class ConfigError(Exception):
    """Raised when the configuration file is missing or malformed."""


class Config:
    """Loads and validates bot configuration from a YAML file.

    Parameters
    ----------
    path:
        Path to the YAML configuration file.  Defaults to ``config.yaml``
        in the repository root.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
        if not config_path.exists():
            raise ConfigError(
                f"Configuration file not found: {config_path}\n"
                "Copy config.example.yaml to config.yaml and fill in your credentials."
            )
        with config_path.open("r") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        self._validate(raw)
        self._data = raw

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self, data: dict[str, Any]) -> None:
        required_sections = ("exchange", "trading", "strategy")
        for section in required_sections:
            if section not in data:
                raise ConfigError(f"Missing required config section: '{section}'")

        exchange = data["exchange"]
        for key in ("id", "api_key", "api_secret"):
            if not exchange.get(key):
                raise ConfigError(f"exchange.{key} must be set in config.yaml")

        trading = data["trading"]
        for key in ("symbol", "trade_amount"):
            if not trading.get(key):
                raise ConfigError(f"trading.{key} must be set in config.yaml")

        if not data.get("strategy", {}).get("name"):
            raise ConfigError("strategy.name must be set in config.yaml")

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def exchange_id(self) -> str:
        return self._data["exchange"]["id"]

    @property
    def api_key(self) -> str:
        return self._data["exchange"]["api_key"]

    @property
    def api_secret(self) -> str:
        return self._data["exchange"]["api_secret"]

    @property
    def sandbox(self) -> bool:
        return bool(self._data["exchange"].get("sandbox", False))

    @property
    def symbol(self) -> str:
        return self._data["trading"]["symbol"]

    @property
    def trade_amount(self) -> float:
        return float(self._data["trading"]["trade_amount"])

    @property
    def max_open_positions(self) -> int:
        return int(self._data["trading"].get("max_open_positions", 1))

    @property
    def risk_per_trade(self) -> float:
        return float(self._data["trading"].get("risk_per_trade", 0.01))

    @property
    def strategy_name(self) -> str:
        return self._data["strategy"]["name"]

    @property
    def strategy_params(self) -> dict[str, Any]:
        return dict(self._data["strategy"].get("params", {}))

    @property
    def timeframe(self) -> str:
        return self._data.get("timeframe", "1h")

    @property
    def candle_limit(self) -> int:
        return int(self._data.get("candle_limit", 100))

    @property
    def log_level(self) -> str:
        return self._data.get("logging", {}).get("level", "INFO")

    @property
    def log_file(self) -> str:
        return self._data.get("logging", {}).get("file", "logs/beast_trader.log")

    def get(self, key: str, default: Any = None) -> Any:
        """Return a top-level config value by key."""
        return self._data.get(key, default)
