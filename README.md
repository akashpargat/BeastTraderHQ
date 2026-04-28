# BeastTraderHQ 🐉

An automated cryptocurrency trading bot built with Python and [CCXT](https://ccxt.org).

---

## Features

| Feature | Details |
|---|---|
| **Exchange connectivity** | Any exchange supported by CCXT (Binance, Coinbase, Kraken, Bybit, OKX, …) |
| **Strategies** | Moving Average Crossover, RSI mean-reversion |
| **Paper trading** | Sandbox / paper-trading mode for risk-free testing |
| **Configurable** | All parameters in a single YAML config file |
| **Extensible** | Drop-in strategy interface – add your own in minutes |
| **Tested** | 40 unit tests covering config, strategies and the orchestrator |

---

## Project structure

```
BeastTraderHQ/
├── bot/
│   ├── config.py            # Config loader & validator
│   ├── logger.py            # Logging setup
│   ├── trader.py            # Main orchestrator (BeastTrader)
│   ├── exchange/
│   │   └── client.py        # CCXT exchange wrapper
│   └── strategies/
│       ├── base.py          # BaseStrategy & Signal
│       ├── moving_average.py# EMA crossover strategy
│       ├── rsi.py           # RSI mean-reversion strategy
│       └── registry.py      # Strategy name → class mapping
├── tests/
│   ├── test_config.py
│   ├── test_strategies.py
│   └── test_trader.py
├── main.py                  # CLI entry point
├── config.example.yaml      # Template – copy to config.yaml
├── requirements.txt
└── .gitignore
```

---

## Quick start

### 1 – Clone & install dependencies

```bash
git clone https://github.com/akashpargat/BeastTraderHQ.git
cd BeastTraderHQ
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2 – Configure the bot

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` and fill in your exchange credentials and preferred settings:

```yaml
exchange:
  id: binance          # CCXT exchange ID
  api_key: "YOUR_API_KEY"
  api_secret: "YOUR_API_SECRET"
  sandbox: true        # Start in paper-trading mode!

trading:
  symbol: "BTC/USDT"
  trade_amount: 50.0   # Quote-currency amount per trade

strategy:
  name: moving_average_crossover
  params:
    fast_period: 9
    slow_period: 21
```

> **⚠️ Security:** `config.yaml` is listed in `.gitignore` and will **never** be committed.  
> Never share your API keys.

### 3 – Run the bot

```bash
python main.py                        # uses config.yaml, 60-second interval
python main.py --interval 300         # 5-minute cycles
python main.py --config my.yaml       # custom config path
```

---

## Strategies

### `moving_average_crossover`

Dual EMA crossover:
- **BUY** when the fast EMA crosses *above* the slow EMA (golden cross)
- **SELL** when the fast EMA crosses *below* the slow EMA (death cross)

| Parameter | Default | Description |
|---|---|---|
| `fast_period` | `9` | Fast EMA period (candles) |
| `slow_period` | `21` | Slow EMA period (candles) |

### `rsi`

RSI mean-reversion:
- **BUY** when RSI crosses *up* through the oversold level
- **SELL** when RSI crosses *down* through the overbought level

| Parameter | Default | Description |
|---|---|---|
| `rsi_period` | `14` | RSI lookback period |
| `rsi_oversold` | `30` | Oversold threshold |
| `rsi_overbought` | `70` | Overbought threshold |

---

## Adding a custom strategy

1. Create `bot/strategies/my_strategy.py` and subclass `BaseStrategy`:

```python
from bot.strategies.base import BaseStrategy, Signal
import pandas as pd

class MyStrategy(BaseStrategy):
    def generate_signal(self, candles: pd.DataFrame) -> Signal:
        self._validate_candles(candles, 10)
        # … your logic …
        return Signal(Signal.BUY, float(candles["close"].iloc[-1]))
```

2. Register it in `bot/strategies/registry.py`:

```python
from .my_strategy import MyStrategy

_REGISTRY["my_strategy"] = MyStrategy
```

3. Set `strategy.name: my_strategy` in `config.yaml`.

---

## Running the tests

```bash
pytest tests/ -v
```

---

## Disclaimer

This software is provided for educational and research purposes only.  
**Use at your own risk.**  Cryptocurrency trading carries significant financial risk.  
Always test with paper trading before using real funds.
