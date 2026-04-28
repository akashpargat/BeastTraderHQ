"""Logging setup for BeastTraderHQ."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def get_logger(name: str = "beast_trader", level: str = "INFO", log_file: str | None = None) -> logging.Logger:
    """Return a configured logger instance.

    Parameters
    ----------
    name:
        Logger name (used as a namespace prefix in log messages).
    level:
        Logging level string: DEBUG, INFO, WARNING, ERROR.
    log_file:
        Optional path to a file where logs are also written.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        # Already configured – return as-is to avoid duplicate handlers.
        return logger

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    fmt = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger
