"""Entry point for BeastTraderHQ.

Usage
-----
    python main.py [--config path/to/config.yaml] [--interval 60]

The bot reads its configuration from ``config.yaml`` (copy
``config.example.yaml`` as a starting point), connects to the configured
exchange, and runs the configured strategy in a loop.
"""

from __future__ import annotations

import argparse
import sys

from bot.config import Config, ConfigError
from bot.trader import BeastTrader


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="BeastTraderHQ – automated crypto trading bot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        metavar="FILE",
        help="Path to the YAML configuration file.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        metavar="SECONDS",
        help="Seconds to sleep between trading cycles.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = Config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    trader = BeastTrader(config)
    trader.run(interval_seconds=args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
