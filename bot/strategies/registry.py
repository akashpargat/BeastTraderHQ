"""Strategy registry – maps strategy name strings to their classes."""

from __future__ import annotations

from typing import Any

from .base import BaseStrategy
from .moving_average import MovingAverageCrossoverStrategy
from .rsi import RSIStrategy

_REGISTRY: dict[str, type[BaseStrategy]] = {
    "moving_average_crossover": MovingAverageCrossoverStrategy,
    "rsi": RSIStrategy,
}


def get_strategy(name: str, params: dict[str, Any] | None = None) -> BaseStrategy:
    """Instantiate and return the strategy identified by *name*.

    Parameters
    ----------
    name:
        Strategy identifier, e.g. ``"moving_average_crossover"`` or ``"rsi"``.
    params:
        Hyper-parameter dictionary forwarded to the strategy constructor.

    Raises
    ------
    KeyError
        If *name* is not a registered strategy.
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown strategy {name!r}. Available strategies: {available}")
    return _REGISTRY[name](params)
