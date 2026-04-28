"""
Beast v2.0 — Backtesting Engine (TradingView Powered)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uses TradingView Premium for ALL historical data and indicators.
TV already has RSI, MACD, VWAP, BB, EMA calculated — we just READ them.

Why TV instead of Alpaca:
  - Alpaca free tier blocks SIP data (403 error)
  - TV Premium has YEARS of data with ALL indicators pre-calculated
  - TV has our custom Pine strategies already running
  - Same data source we use for live trading = no backtest/live gap

Usage:
    python backtest_engine.py                    # Backtest all strategies
    python backtest_engine.py --stock NVDA       # Single stock
    python backtest_engine.py --strategy I       # Single strategy
    python backtest_engine.py --bars 500         # Custom bar count
"""
import os
import sys
import time
import logging
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv('.env')

from tv_cdp_client import TVClient

log = logging.getLogger('Beast.Backtest')
ET = ZoneInfo("America/New_York")


@dataclass
class BacktestTrade:
    symbol: str
    strategy: str
    entry_price: float
    exit_price: float
    entry_time: str
    exit_time: str
    pnl: float
    pnl_pct: float
    regime: str = ''
    hold_bars: int = 0


@dataclass
class BacktestResult:
    strategy: str
    symbol: str
    regime: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0
    win_rate: float = 0
    avg_pnl: float = 0
    max_win: float = 0
    max_loss: float = 0
    profit_factor: float = 0
    max_drawdown: float = 0
    trade_list: list = field(default_factory=list)


class BacktestEngine:
    """Backtests strategies using TradingView Premium data."""

    def __init__(self):
        self.tv = TVClient()
        if not self.tv.health_check():
            log.warning("⚠️ TradingView not connected. Start TV Desktop with --remote-debugging-port=9222")
        else:
            self.tv._connect()
            log.info("📺 Backtest engine connected to TradingView Premium")

    def get_bars(self, symbol: str, count: int = 500, timeframe: str = '1D') -> list[dict]:
        """Fetch historical bars from TradingView via CDP.
        Uses the same OHLCV data path as the MCP server."""
        
        # Switch symbol and timeframe on TV
        self.tv.set_symbol(symbol)
        time.sleep(2)
        
        # Read OHLCV bars using the proven MCP path
        js = f"""
        (function() {{
            var bars = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget.model().mainSeries().bars();
            if (!bars || typeof bars.lastIndex !== 'function') return null;
            var result = [];
            var end = bars.lastIndex();
            var start = Math.max(bars.firstIndex(), end - {count} + 1);
            for (var i = start; i <= end; i++) {{
                var v = bars.valueAt(i);
                if (v) result.push({{time: v[0], open: v[1], high: v[2], low: v[3], close: v[4], volume: v[5] || 0}});
            }}
            return result;
        }})()
        """
        try:
            data = self.tv._evaluate(js)
            if data and isinstance(data, list):
                log.info(f"  📺 Got {len(data)} bars for {symbol} from TradingView")
                return data
            return []
        except Exception as e:
            log.error(f"  ❌ TV bars fetch failed for {symbol}: {e}")
            return []

    def get_bars_with_indicators(self, symbol: str, count: int = 200) -> list[dict]:
        """Fetch bars AND indicator values from TV in one shot.
        Returns bars enriched with RSI, MACD, VWAP, EMA, BB."""
        
        self.tv.set_symbol(symbol)
        time.sleep(2.5)
        
        # Get raw OHLCV
        bars = self.get_bars(symbol, count)
        if not bars:
            return []
        
        # Get current indicator values (these are for the LAST bar only)
        studies = self.tv.get_study_values()
        
        # Parse indicators
        indicators = {}
        for s in studies:
            name = s.get('name', '')
            vals = s.get('values', {})
            if 'Relative Strength' in name:
                indicators['rsi'] = self._parse_float(vals.get('RSI', '50'))
            elif name == 'MACD':
                indicators['macd'] = self._parse_float(vals.get('MACD', '0'))
                indicators['macd_signal'] = self._parse_float(vals.get('Signal', '0'))
                indicators['macd_hist'] = self._parse_float(vals.get('Histogram', '0'))
            elif name == 'VWAP':
                indicators['vwap'] = self._parse_float(vals.get('VWAP', '0'))
            elif name == 'Bollinger Bands':
                indicators['bb_upper'] = self._parse_float(vals.get('Upper', '0'))
                indicators['bb_mid'] = self._parse_float(vals.get('Basis', '0'))
                indicators['bb_lower'] = self._parse_float(vals.get('Lower', '0'))
            elif 'Moving Average Exponential' in name:
                indicators.setdefault('ema', self._parse_float(vals.get('MA', '0')))
            elif 'Moving Average' in name and 'Exponential' not in name:
                indicators['sma'] = self._parse_float(vals.get('MA', '0'))
        
        return bars, indicators
    
    def _parse_float(self, val) -> float:
        try:
            return float(str(val).replace('\u2212', '-').replace(',', '').replace('\u2205', '0'))
        except Exception:
            return 0.0

    def _calc_rsi(self, closes: list, period: int = 14) -> list[float]:
        """Calculate RSI series."""
        rsi_series = [50.0] * len(closes)
        if len(closes) < period + 1:
            return rsi_series
        deltas = np.diff(closes)
        for i in range(period, len(deltas)):
            gains = deltas[max(0, i-period):i]
            avg_gain = np.mean(np.where(gains > 0, gains, 0))
            avg_loss = np.mean(np.where(gains < 0, -gains, 0))
            if avg_loss == 0:
                rsi_series[i+1] = 100
            else:
                rs = avg_gain / avg_loss
                rsi_series[i+1] = 100 - (100 / (1 + rs))
        return rsi_series

    def _calc_sma(self, values: list, period: int) -> list[float]:
        result = [0.0] * len(values)
        for i in range(period - 1, len(values)):
            result[i] = np.mean(values[i-period+1:i+1])
        return result

    def _calc_ema(self, values: list, period: int) -> list[float]:
        result = [0.0] * len(values)
        alpha = 2 / (period + 1)
        result[0] = values[0]
        for i in range(1, len(values)):
            result[i] = alpha * values[i] + (1 - alpha) * result[i-1]
        return result

    # ── Strategy Implementations ───────────────────────

    def _strategy_mean_reversion(self, bars: list, symbol: str) -> list[BacktestTrade]:
        """Strategy I: Blue Chip Mean Reversion. Buy RSI < 30, sell RSI > 50."""
        trades = []
        closes = [b['close'] for b in bars]
        rsi = self._calc_rsi(closes)
        
        in_trade = False
        entry_price = 0
        entry_idx = 0

        for i in range(30, len(bars)):
            if not in_trade and rsi[i] < 30:
                in_trade = True
                entry_price = bars[i]['close']
                entry_idx = i
            elif in_trade and (rsi[i] > 50 or i - entry_idx > 60):  # Exit at RSI 50 or 60 bars
                exit_price = bars[i]['close']
                pnl = (exit_price - entry_price) * 100  # Assume 100 shares
                trades.append(BacktestTrade(
                    symbol=symbol, strategy='I:MeanReversion',
                    entry_price=entry_price, exit_price=exit_price,
                    entry_time=bars[entry_idx]['time'], exit_time=bars[i]['time'],
                    pnl=pnl, pnl_pct=(exit_price - entry_price) / entry_price,
                    hold_bars=i - entry_idx,
                ))
                in_trade = False
        return trades

    def _strategy_sma_trend(self, bars: list, symbol: str) -> list[BacktestTrade]:
        """Strategy J: SMA Trend Follow. Buy when EMA9 > EMA21, sell when EMA9 < EMA21."""
        trades = []
        closes = [b['close'] for b in bars]
        ema9 = self._calc_ema(closes, 9)
        ema21 = self._calc_ema(closes, 21)

        in_trade = False
        entry_price = 0
        entry_idx = 0

        for i in range(25, len(bars)):
            if not in_trade and ema9[i] > ema21[i] and ema9[i-1] <= ema21[i-1]:
                in_trade = True
                entry_price = bars[i]['close']
                entry_idx = i
            elif in_trade and (ema9[i] < ema21[i] or i - entry_idx > 120):
                exit_price = bars[i]['close']
                pnl = (exit_price - entry_price) * 50  # 50 shares
                trades.append(BacktestTrade(
                    symbol=symbol, strategy='J:SMA_Trend',
                    entry_price=entry_price, exit_price=exit_price,
                    entry_time=bars[entry_idx]['time'], exit_time=bars[i]['time'],
                    pnl=pnl, pnl_pct=(exit_price - entry_price) / entry_price,
                    hold_bars=i - entry_idx,
                ))
                in_trade = False
        return trades

    def _strategy_rsi_bounce(self, bars: list, symbol: str) -> list[BacktestTrade]:
        """Strategy G: Red to Green / Akash Method. Buy RSI < 35, sell +2%."""
        trades = []
        closes = [b['close'] for b in bars]
        rsi = self._calc_rsi(closes)

        in_trade = False
        entry_price = 0
        entry_idx = 0

        for i in range(20, len(bars)):
            if not in_trade and rsi[i] < 35:
                in_trade = True
                entry_price = bars[i]['close']
                entry_idx = i
            elif in_trade:
                current = bars[i]['close']
                gain = (current - entry_price) / entry_price
                # Exit at +2% (scalp target) or -1.5% stop or 30 bars timeout
                if gain >= 0.02 or gain <= -0.015 or i - entry_idx > 30:
                    pnl = (current - entry_price) * 200  # 200 shares (cheap stocks)
                    trades.append(BacktestTrade(
                        symbol=symbol, strategy='G:Akash_Method',
                        entry_price=entry_price, exit_price=current,
                        entry_time=bars[entry_idx]['time'], exit_time=bars[i]['time'],
                        pnl=pnl, pnl_pct=gain,
                        hold_bars=i - entry_idx,
                    ))
                    in_trade = False
        return trades

    def _strategy_vwap_bounce(self, bars: list, symbol: str) -> list[BacktestTrade]:
        """Strategy B: VWAP Bounce. Buy when price touches VWAP from above."""
        trades = []
        closes = [b['close'] for b in bars]
        highs = [b['high'] for b in bars]
        lows = [b['low'] for b in bars]
        volumes = [b['volume'] for b in bars]

        in_trade = False
        entry_price = 0
        entry_idx = 0

        # Calculate running VWAP
        cum_pv = 0
        cum_vol = 0
        vwap = [0.0] * len(bars)
        for i in range(len(bars)):
            typical = (highs[i] + lows[i] + closes[i]) / 3
            cum_pv += typical * volumes[i]
            cum_vol += volumes[i]
            vwap[i] = cum_pv / cum_vol if cum_vol > 0 else closes[i]

        for i in range(30, len(bars)):
            if not in_trade:
                # Price was above VWAP, dipped to touch it
                if closes[i-1] > vwap[i-1] and lows[i] <= vwap[i] * 1.001 and closes[i] > vwap[i]:
                    in_trade = True
                    entry_price = closes[i]
                    entry_idx = i
            elif in_trade:
                current = closes[i]
                gain = (current - entry_price) / entry_price
                if gain >= 0.015 or gain <= -0.01 or i - entry_idx > 20:
                    pnl = (current - entry_price) * 50
                    trades.append(BacktestTrade(
                        symbol=symbol, strategy='B:VWAP_Bounce',
                        entry_price=entry_price, exit_price=current,
                        entry_time=bars[entry_idx]['time'], exit_time=bars[i]['time'],
                        pnl=pnl, pnl_pct=gain,
                        hold_bars=i - entry_idx,
                    ))
                    in_trade = False
        return trades

    # ── Run Backtest ───────────────────────────────────

    def backtest(self, symbol: str, bar_count: int = 500, 
                 strategies: list = None) -> list[BacktestResult]:
        """Run all strategies on a symbol using TV data."""
        print(f"  📊 Loading {symbol} from TradingView ({bar_count} bars)...")
        bars = self.get_bars(symbol, bar_count)
        if len(bars) < 50:
            print(f"  ⚠️ Only {len(bars)} bars — need 50+ for backtest")
            return []

        print(f"  📊 Got {len(bars)} bars from TV. Running strategies...")

        all_strategies = {
            'I': self._strategy_mean_reversion,
            'J': self._strategy_sma_trend,
            'G': self._strategy_rsi_bounce,
            'B': self._strategy_vwap_bounce,
        }

        if strategies:
            all_strategies = {k: v for k, v in all_strategies.items() if k in strategies}

        results = []
        for strat_key, strat_fn in all_strategies.items():
            trades = strat_fn(bars, symbol)
            
            if not trades:
                results.append(BacktestResult(
                    strategy=strat_key, symbol=symbol, regime='ALL', trades=0
                ))
                continue

            wins = [t for t in trades if t.pnl > 0]
            losses = [t for t in trades if t.pnl <= 0]
            total_pnl = sum(t.pnl for t in trades)
            
            avg_win = np.mean([t.pnl for t in wins]) if wins else 0
            avg_loss = np.mean([abs(t.pnl) for t in losses]) if losses else 1
            
            # Max drawdown
            equity_curve = [0]
            for t in trades:
                equity_curve.append(equity_curve[-1] + t.pnl)
            peak = 0
            max_dd = 0
            for eq in equity_curve:
                if eq > peak:
                    peak = eq
                dd = peak - eq
                if dd > max_dd:
                    max_dd = dd

            result = BacktestResult(
                strategy=strat_key,
                symbol=symbol,
                regime='ALL',
                trades=len(trades),
                wins=len(wins),
                losses=len(losses),
                total_pnl=total_pnl,
                win_rate=len(wins) / len(trades) if trades else 0,
                avg_pnl=total_pnl / len(trades) if trades else 0,
                max_win=max(t.pnl for t in trades) if trades else 0,
                max_loss=min(t.pnl for t in trades) if trades else 0,
                profit_factor=avg_win / avg_loss if avg_loss > 0 else 0,
                max_drawdown=max_dd,
                trade_list=trades,
            )
            results.append(result)

        return results

    def backtest_portfolio(self, symbols: list = None, bar_count: int = 500) -> str:
        """Backtest all strategies across multiple stocks using TV data."""
        if not symbols:
            symbols = ['NVDA', 'AMD', 'INTC', 'GOOGL', 'AMZN', 'AAPL',
                       'META', 'TSLA', 'NOK', 'CRM', 'PLTR', 'ORCL']

        all_results = []
        for sym in symbols:
            results = self.backtest(sym, bar_count)
            all_results.extend(results)

        # Format report
        lines = ["🔬 BACKTEST RESULTS", f"Bars: {bar_count} | Stocks: {len(symbols)}", ""]

        # Aggregate by strategy
        strategy_agg = {}
        for r in all_results:
            if r.strategy not in strategy_agg:
                strategy_agg[r.strategy] = {
                    'trades': 0, 'wins': 0, 'total_pnl': 0, 'symbols': []
                }
            strategy_agg[r.strategy]['trades'] += r.trades
            strategy_agg[r.strategy]['wins'] += r.wins
            strategy_agg[r.strategy]['total_pnl'] += r.total_pnl
            if r.trades > 0:
                strategy_agg[r.strategy]['symbols'].append(r.symbol)

        lines.append("📋 BY STRATEGY:")
        for strat, agg in sorted(strategy_agg.items(), key=lambda x: x[1]['total_pnl'], reverse=True):
            wr = agg['wins'] / agg['trades'] * 100 if agg['trades'] > 0 else 0
            emoji = "🟢" if agg['total_pnl'] > 0 else "🔴"
            lines.append(f"{emoji} {strat:5s} {agg['trades']:4d} trades "
                        f"WR:{wr:>5.1f}% P&L:${agg['total_pnl']:>+9.2f} "
                        f"Stocks: {', '.join(agg['symbols'][:5])}")

        # Best individual combos
        profitable = [r for r in all_results if r.total_pnl > 0]
        profitable.sort(key=lambda x: x.total_pnl, reverse=True)
        if profitable:
            lines.append("")
            lines.append("🏆 TOP COMBOS:")
            for r in profitable[:5]:
                lines.append(f"  🟢 {r.symbol} + {r.strategy}: ${r.total_pnl:+.2f} "
                           f"({r.win_rate:.0%} WR, {r.trades} trades)")

        # Worst combos
        losing = [r for r in all_results if r.total_pnl < 0]
        losing.sort(key=lambda x: x.total_pnl)
        if losing:
            lines.append("")
            lines.append("💀 WORST COMBOS:")
            for r in losing[:5]:
                lines.append(f"  🔴 {r.symbol} + {r.strategy}: ${r.total_pnl:+.2f} "
                           f"({r.win_rate:.0%} WR)")

        return "\n".join(lines)


# ── CLI Entry Point ────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Beast Backtesting Engine (TradingView Powered)')
    parser.add_argument('--stock', type=str, help='Single stock to backtest')
    parser.add_argument('--strategy', type=str, help='Single strategy (I, J, G, B)')
    parser.add_argument('--bars', type=int, default=500, help='Number of bars from TV')
    args = parser.parse_args()

    engine = BacktestEngine()

    if args.stock:
        strategies = [args.strategy] if args.strategy else None
        results = engine.backtest(args.stock.upper(), args.bars, strategies)
        for r in results:
            emoji = "🟢" if r.total_pnl > 0 else "🔴"
            print(f"{emoji} {r.symbol} + {r.strategy}: "
                  f"{r.trades} trades, WR:{r.win_rate:.0%}, "
                  f"P&L:${r.total_pnl:+.2f}, MaxDD:${r.max_drawdown:.2f}")
    else:
        report = engine.backtest_portfolio(bar_count=args.bars)
        print(report)
