"""
Beast v2.0 — Strategy Optimizer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uses backtest results to find optimal parameters per stock per regime.
Answers: "What RSI threshold, target %, and stop % works best for NVDA in BULL?"

Usage:
    python strategy_optimizer.py                 # Optimize all
    python strategy_optimizer.py --stock NVDA    # Single stock
"""
import os
import sys
import logging
import numpy as np
from datetime import datetime
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv('.env')

from tv_cdp_client import TVClient
from backtest_engine import BacktestEngine, BacktestTrade

log = logging.getLogger('Beast.Optimizer')


@dataclass
class OptimizedParams:
    symbol: str
    strategy: str
    rsi_buy: float          # Best RSI entry threshold
    target_pct: float       # Best profit target %
    stop_pct: float         # Best stop loss %
    win_rate: float
    total_pnl: float
    trades: int
    improvement_pct: float  # How much better than default


class StrategyOptimizer:
    """Finds optimal strategy parameters using TV backtest data."""

    def __init__(self):
        self.engine = BacktestEngine()

    def optimize_rsi_bounce(self, symbol: str, bars: list) -> OptimizedParams:
        """Test RSI thresholds from 25-40, targets from 1.5%-4%, stops from 1%-2.5%."""
        best = None
        closes = [b['close'] for b in bars]
        rsi_series = self.engine._calc_rsi(closes)

        rsi_range = [25, 28, 30, 33, 35, 38, 40]
        target_range = [0.015, 0.02, 0.025, 0.03, 0.035, 0.04]
        stop_range = [0.01, 0.012, 0.015, 0.018, 0.02, 0.025]

        for rsi_thresh in rsi_range:
            for target in target_range:
                for stop in stop_range:
                    trades = self._run_rsi_backtest(bars, rsi_series, rsi_thresh, target, stop)
                    if len(trades) < 3:
                        continue

                    pnl = sum(t.pnl for t in trades)
                    wins = sum(1 for t in trades if t.pnl > 0)
                    wr = wins / len(trades)

                    if best is None or pnl > best.total_pnl:
                        best = OptimizedParams(
                            symbol=symbol, strategy='G:Akash_Method',
                            rsi_buy=rsi_thresh, target_pct=target,
                            stop_pct=stop, win_rate=wr,
                            total_pnl=pnl, trades=len(trades),
                            improvement_pct=0,
                        )

        # Calculate improvement vs default (RSI 35, target 2%, stop 1.5%)
        if best:
            default_trades = self._run_rsi_backtest(bars, rsi_series, 35, 0.02, 0.015)
            default_pnl = sum(t.pnl for t in default_trades) if default_trades else 0
            if default_pnl != 0:
                best.improvement_pct = (best.total_pnl - default_pnl) / abs(default_pnl)

        return best

    def optimize_mean_reversion(self, symbol: str, bars: list) -> OptimizedParams:
        """Test RSI entry from 25-35, exit from 45-60."""
        best = None
        closes = [b['close'] for b in bars]
        rsi_series = self.engine._calc_rsi(closes)

        entry_range = [25, 28, 30, 33, 35]
        exit_range = [45, 48, 50, 53, 55, 60]

        for entry_rsi in entry_range:
            for exit_rsi in exit_range:
                trades = []
                in_trade = False
                entry_price = 0
                entry_idx = 0

                for i in range(30, len(bars)):
                    if not in_trade and rsi_series[i] < entry_rsi:
                        in_trade = True
                        entry_price = bars[i]['close']
                        entry_idx = i
                    elif in_trade and (rsi_series[i] > exit_rsi or i - entry_idx > 60):
                        exit_price = bars[i]['close']
                        pnl = (exit_price - entry_price) * 100
                        trades.append(BacktestTrade(
                            symbol=symbol, strategy='I', entry_price=entry_price,
                            exit_price=exit_price, pnl=pnl,
                            pnl_pct=(exit_price - entry_price) / entry_price,
                            entry_time='', exit_time='', hold_bars=i - entry_idx,
                        ))
                        in_trade = False

                if len(trades) < 3:
                    continue

                pnl = sum(t.pnl for t in trades)
                wins = sum(1 for t in trades if t.pnl > 0)

                if best is None or pnl > best.total_pnl:
                    best = OptimizedParams(
                        symbol=symbol, strategy='I:MeanReversion',
                        rsi_buy=entry_rsi, target_pct=exit_rsi / 100,
                        stop_pct=0, win_rate=wins / len(trades),
                        total_pnl=pnl, trades=len(trades),
                        improvement_pct=0,
                    )

        return best

    def _run_rsi_backtest(self, bars, rsi, rsi_thresh, target, stop):
        trades = []
        in_trade = False
        entry_price = 0
        entry_idx = 0
        closes = [b['close'] for b in bars]

        for i in range(20, len(bars)):
            if not in_trade and rsi[i] < rsi_thresh:
                in_trade = True
                entry_price = closes[i]
                entry_idx = i
            elif in_trade:
                gain = (closes[i] - entry_price) / entry_price
                if gain >= target or gain <= -stop or i - entry_idx > 30:
                    pnl = (closes[i] - entry_price) * 200
                    trades.append(BacktestTrade(
                        symbol='', strategy='G', entry_price=entry_price,
                        exit_price=closes[i], pnl=pnl, pnl_pct=gain,
                        entry_time='', exit_time='', hold_bars=i - entry_idx,
                    ))
                    in_trade = False
        return trades

    def optimize_stock(self, symbol: str, bar_count: int = 300) -> list[OptimizedParams]:
        """Optimize all strategies for a single stock."""
        bars = self.engine.get_bars(symbol, bar_count)
        if len(bars) < 50:
            return []

        results = []

        # Optimize Akash Method (G)
        g = self.optimize_rsi_bounce(symbol, bars)
        if g:
            results.append(g)

        # Optimize Mean Reversion (I)
        i = self.optimize_mean_reversion(symbol, bars)
        if i:
            results.append(i)

        return results

    def optimize_portfolio(self, symbols: list = None, bar_count: int = 300) -> str:
        """Optimize all stocks and return formatted report."""
        if not symbols:
            symbols = ['NVDA', 'AMD', 'INTC', 'GOOGL', 'AMZN', 'META',
                       'TSLA', 'NOK', 'CRM', 'PLTR', 'MU', 'ORCL']

        lines = ["🔧 STRATEGY OPTIMIZER RESULTS", f"Stocks: {len(symbols)} | Bars: {bar_count}", ""]
        lines.append("📋 OPTIMAL PARAMETERS:")
        lines.append(f"{'STOCK':6s} {'STRATEGY':15s} {'RSI':>4s} {'TARGET':>7s} {'STOP':>6s} "
                     f"{'WR':>5s} {'P&L':>10s} {'vs DEFAULT':>10s}")
        lines.append("─" * 70)

        all_results = []
        for sym in symbols:
            print(f"  🔧 Optimizing {sym}...")
            results = self.optimize_stock(sym, bar_count)
            for r in results:
                imp = f"+{r.improvement_pct:.0%}" if r.improvement_pct > 0 else f"{r.improvement_pct:.0%}"
                lines.append(f"{r.symbol:6s} {r.strategy:15s} {r.rsi_buy:>4.0f} "
                            f"{r.target_pct:>6.1%} {r.stop_pct:>5.1%} "
                            f"{r.win_rate:>4.0%} ${r.total_pnl:>+9.2f} {imp:>10s}")
                all_results.append(r)

        # Summary
        if all_results:
            best = max(all_results, key=lambda r: r.total_pnl)
            lines.append("")
            lines.append(f"🏆 BEST OVERALL: {best.symbol} + {best.strategy}")
            lines.append(f"   RSI entry: {best.rsi_buy} | Target: {best.target_pct:.1%} | "
                        f"Stop: {best.stop_pct:.1%}")
            lines.append(f"   P&L: ${best.total_pnl:+,.2f} | WR: {best.win_rate:.0%} | "
                        f"{best.trades} trades")

        return "\n".join(lines)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Beast Strategy Optimizer (TV Powered)')
    parser.add_argument('--stock', type=str, help='Single stock to optimize')
    parser.add_argument('--bars', type=int, default=300, help='Bar count')
    args = parser.parse_args()

    optimizer = StrategyOptimizer()

    if args.stock:
        results = optimizer.optimize_stock(args.stock.upper(), args.bars)
        for r in results:
            print(f"🔧 {r.symbol} {r.strategy}: RSI<{r.rsi_buy} "
                  f"Target:{r.target_pct:.1%} Stop:{r.stop_pct:.1%} "
                  f"WR:{r.win_rate:.0%} P&L:${r.total_pnl:+,.2f} "
                  f"({r.improvement_pct:+.0%} vs default)")
    else:
        report = optimizer.optimize_portfolio(bar_count=args.bars)
        print(report)
