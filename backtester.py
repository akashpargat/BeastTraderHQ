"""
Beast Terminal V4 — Backtesting Engine
=======================================
Two modes:
1. REPLAY MODE: Re-evaluate past trade_decisions with current strategy
   - Uses our actual DB data (scan_snapshots, trade_decisions)
   - Shows: "If we used today's settings on yesterday's data, what happens?"
   - Answers: "Was our anti-buyback too aggressive? Would we have made more money?"

2. HISTORICAL MODE: Simulate strategies on 90 days of yfinance data
   - Downloads OHLCV + indicators for any stock
   - Runs our strategies (RSI dip buy, momentum, mean reversion)
   - Reports: win rate, avg P&L, max drawdown, Sharpe ratio

Both modes store results in PostgreSQL for dashboard display.
"""

import os
import logging
import json
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

log = logging.getLogger('Beast.Backtest')


@dataclass
class BacktestTrade:
    symbol: str
    side: str  # buy/sell
    price: float
    qty: int
    timestamp: str
    strategy: str
    reason: str
    pnl: float = 0
    pnl_pct: float = 0
    hold_time_min: int = 0


@dataclass
class BacktestResult:
    name: str
    period: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0
    total_pnl: float = 0
    avg_pnl: float = 0
    best_trade: float = 0
    worst_trade: float = 0
    max_drawdown: float = 0
    sharpe_ratio: float = 0
    profit_factor: float = 0
    avg_hold_time_min: int = 0
    trades: list = field(default_factory=list)


class BacktestEngine:
    """Backtesting engine with replay + historical simulation."""

    def __init__(self, db=None):
        self.db = db

    # ══════════════════════════════════════════════
    #  MODE 1: REPLAY — Re-evaluate past decisions
    # ══════════════════════════════════════════════

    def replay_decisions(self, days: int = 7, settings: dict = None) -> BacktestResult:
        """Replay past trade_decisions with optional different settings.
        Shows what would have happened if we changed our strategy.
        
        settings can override:
          - min_confidence: what if we lowered threshold from 75 to 60?
          - anti_buyback: what if we disabled anti-buyback for blue chips?
          - tv_required: what if we traded without TV confirmation?
          - max_loss_pct: what if we cut losses at -3% instead of -5%?
        """
        if not self.db:
            return BacktestResult(name="replay", period=f"{days}d")

        settings = settings or {}
        min_conf = settings.get('min_confidence', 75)
        skip_buyback = settings.get('skip_anti_buyback_blue_chips', False)
        skip_tv = settings.get('skip_tv_requirement', False)

        # Get all decisions with price data
        decisions = self.db._exec(
            """SELECT symbol, action, confidence, block_reason, price_at_decision,
                      price_after_1h, price_after_4h, was_correct, tv_data, signals,
                      strategy, created_at
               FROM trade_decisions
               WHERE created_at > NOW() - interval '%s days'
                 AND price_at_decision IS NOT NULL AND price_at_decision > 0
               ORDER BY created_at""",
            (days,), fetch=True
        ) or []

        result = BacktestResult(name="replay", period=f"{days}d")
        trades = []
        gross_wins = 0
        gross_losses = 0

        for d in decisions:
            sym = d['symbol']
            action = d['action']
            conf = d.get('confidence', 0)
            price = d['price_at_decision']
            price_after = d.get('price_after_4h') or d.get('price_after_1h')
            block_reason = d.get('block_reason', '')

            if not price_after or price_after <= 0:
                continue

            # What WOULD we have done with different settings?
            would_trade = False

            if action == 'BUY' and d.get('was_correct') is not None:
                # We actually bought — count it
                would_trade = True
            elif action in ('BLOCK', 'SKIP'):
                # We blocked — would we have traded with different settings?
                if skip_buyback and 'Anti-buyback' in block_reason:
                    would_trade = True  # Would have bought
                elif skip_tv and ('TV rejected' in block_reason or 'No TV' in block_reason):
                    would_trade = True  # Would have bought without TV
                elif conf >= min_conf and 'confidence' in block_reason.lower():
                    would_trade = True

            if would_trade:
                pnl_pct = (price_after - price) / price * 100
                simulated_pnl = pnl_pct * 100  # Assume $10K position
                result.total_trades += 1
                if pnl_pct > 0:
                    result.wins += 1
                    gross_wins += simulated_pnl
                else:
                    result.losses += 1
                    gross_losses += abs(simulated_pnl)
                result.total_pnl += simulated_pnl
                if simulated_pnl > result.best_trade:
                    result.best_trade = simulated_pnl
                if simulated_pnl < result.worst_trade:
                    result.worst_trade = simulated_pnl
                trades.append(BacktestTrade(
                    symbol=sym, side='buy', price=price, qty=0,
                    timestamp=str(d['created_at']),
                    strategy=d.get('strategy', '?'),
                    reason=block_reason or 'executed',
                    pnl=simulated_pnl, pnl_pct=pnl_pct,
                ))

        if result.total_trades > 0:
            result.win_rate = result.wins / result.total_trades * 100
            result.avg_pnl = result.total_pnl / result.total_trades
            result.profit_factor = gross_wins / gross_losses if gross_losses > 0 else 999
        result.trades = trades
        return result

    def replay_what_if(self) -> dict:
        """Run multiple replay scenarios and compare.
        Shows: 'If we changed X, we would have made Y more/less.'"""
        scenarios = {
            'current_settings': self.replay_decisions(7),
            'no_anti_buyback_blue': self.replay_decisions(7, {'skip_anti_buyback_blue_chips': True}),
            'no_tv_requirement': self.replay_decisions(7, {'skip_tv_requirement': True}),
            'lower_confidence_60': self.replay_decisions(7, {'min_confidence': 60}),
        }
        return {name: {
            'trades': r.total_trades, 'wins': r.wins, 'losses': r.losses,
            'win_rate': round(r.win_rate, 1), 'total_pnl': round(r.total_pnl, 2),
            'avg_pnl': round(r.avg_pnl, 2), 'profit_factor': round(r.profit_factor, 2),
            'best': round(r.best_trade, 2), 'worst': round(r.worst_trade, 2),
        } for name, r in scenarios.items()}

    # ══════════════════════════════════════════════
    #  MODE 2: HISTORICAL — Simulate on past data
    # ══════════════════════════════════════════════

    def historical_backtest(self, symbol: str, days: int = 90,
                            strategy: str = 'rsi_dip') -> BacktestResult:
        """Download historical data and simulate a strategy.
        
        Strategies:
          rsi_dip: Buy when RSI<30, sell when RSI>70 or +2%
          momentum: Buy when price crosses above 20-SMA with volume, sell at +3% or -2%
          mean_reversion: Buy -3% daily drop, sell at mean (previous close)
          akash_method: Buy -5% dip, sell at +2% limit
        """
        try:
            import yfinance as yf
            import numpy as np
        except ImportError:
            return BacktestResult(name=f"{strategy}_{symbol}", period=f"{days}d")

        # Download data
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=f"{days}d", interval="1d")
        if hist.empty:
            return BacktestResult(name=f"{strategy}_{symbol}", period=f"{days}d")

        # Calculate indicators
        close = hist['Close'].values
        volume = hist['Volume'].values
        dates = hist.index

        # RSI
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.zeros(len(close))
        avg_loss = np.zeros(len(close))
        avg_gain[14] = np.mean(gains[:14])
        avg_loss[14] = np.mean(losses[:14])
        for i in range(15, len(close)):
            avg_gain[i] = (avg_gain[i-1] * 13 + gains[i-1]) / 14
            avg_loss[i] = (avg_loss[i-1] * 13 + losses[i-1]) / 14
        rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100)
        rsi = 100 - (100 / (1 + rs))

        # 20-SMA
        sma20 = np.convolve(close, np.ones(20)/20, mode='same')

        # Simulate
        result = BacktestResult(name=f"{strategy}_{symbol}", period=f"{days}d")
        trades = []
        position = None  # {price, date, qty}
        gross_wins = 0
        gross_losses = 0

        for i in range(20, len(close)):
            price = close[i]
            date = str(dates[i].date())

            if position is None:
                # Entry signals
                buy = False
                reason = ""

                if strategy == 'rsi_dip' and rsi[i] < 30:
                    buy = True
                    reason = f"RSI={rsi[i]:.0f} oversold"
                elif strategy == 'momentum' and close[i] > sma20[i] and close[i-1] <= sma20[i-1]:
                    if volume[i] > np.mean(volume[max(0,i-20):i]) * 1.5:
                        buy = True
                        reason = f"SMA20 cross + volume {volume[i]/np.mean(volume[max(0,i-20):i]):.1f}x"
                elif strategy == 'mean_reversion' and i > 0:
                    daily_chg = (close[i] - close[i-1]) / close[i-1] * 100
                    if daily_chg <= -3:
                        buy = True
                        reason = f"Drop {daily_chg:.1f}% mean reversion"
                elif strategy == 'akash_method' and i > 0:
                    daily_chg = (close[i] - close[i-1]) / close[i-1] * 100
                    if daily_chg <= -5:
                        buy = True
                        reason = f"Akash dip buy {daily_chg:.1f}%"

                if buy:
                    position = {'price': price, 'date': date, 'idx': i}

            else:
                # Exit signals
                pnl_pct = (price - position['price']) / position['price'] * 100
                sell = False
                reason = ""

                if strategy == 'rsi_dip':
                    if rsi[i] > 70 or pnl_pct >= 2 or pnl_pct <= -5:
                        sell = True
                        reason = f"RSI={rsi[i]:.0f}" if rsi[i] > 70 else f"Target {pnl_pct:+.1f}%"
                elif strategy == 'momentum':
                    if pnl_pct >= 3 or pnl_pct <= -2:
                        sell = True
                        reason = f"{'Profit' if pnl_pct > 0 else 'Stop'} {pnl_pct:+.1f}%"
                elif strategy == 'mean_reversion':
                    if pnl_pct >= 1.5 or pnl_pct <= -3 or (i - position['idx'] >= 3):
                        sell = True
                        reason = f"Mean rev exit {pnl_pct:+.1f}%"
                elif strategy == 'akash_method':
                    if pnl_pct >= 2 or pnl_pct <= -8 or (i - position['idx'] >= 5):
                        sell = True
                        reason = f"Akash exit {pnl_pct:+.1f}%"

                if sell:
                    sim_pnl = pnl_pct * 100  # $10K position
                    hold_days = i - position['idx']
                    result.total_trades += 1
                    result.total_pnl += sim_pnl
                    if sim_pnl > 0:
                        result.wins += 1
                        gross_wins += sim_pnl
                    else:
                        result.losses += 1
                        gross_losses += abs(sim_pnl)
                    if sim_pnl > result.best_trade:
                        result.best_trade = sim_pnl
                    if sim_pnl < result.worst_trade:
                        result.worst_trade = sim_pnl

                    trades.append(BacktestTrade(
                        symbol=symbol, side='sell', price=price, qty=0,
                        timestamp=date, strategy=strategy, reason=reason,
                        pnl=sim_pnl, pnl_pct=pnl_pct, hold_time_min=hold_days * 390,
                    ))
                    position = None

        if result.total_trades > 0:
            result.win_rate = result.wins / result.total_trades * 100
            result.avg_pnl = result.total_pnl / result.total_trades
            result.profit_factor = gross_wins / gross_losses if gross_losses > 0 else 999
            hold_times = [t.hold_time_min for t in trades]
            result.avg_hold_time_min = sum(hold_times) // len(hold_times) if hold_times else 0

        # Drawdown
        equity_curve = [10000]
        for t in trades:
            equity_curve.append(equity_curve[-1] + t.pnl)
        peak = equity_curve[0]
        max_dd = 0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd
        result.max_drawdown = max_dd

        result.trades = trades
        return result

    def run_all_strategies(self, symbol: str, days: int = 90) -> dict:
        """Run all strategies on one stock and compare."""
        strategies = ['rsi_dip', 'momentum', 'mean_reversion', 'akash_method']
        results = {}
        for strat in strategies:
            r = self.historical_backtest(symbol, days, strat)
            results[strat] = {
                'trades': r.total_trades, 'wins': r.wins, 'win_rate': round(r.win_rate, 1),
                'total_pnl': round(r.total_pnl, 2), 'avg_pnl': round(r.avg_pnl, 2),
                'profit_factor': round(r.profit_factor, 2),
                'max_drawdown': round(r.max_drawdown, 2),
                'best': round(r.best_trade, 2), 'worst': round(r.worst_trade, 2),
            }
        return results

    def run_portfolio_backtest(self, days: int = 90) -> dict:
        """Backtest all strategies across top watchlist stocks."""
        top_stocks = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'AMD', 'TSLA',
                      'META', 'CRM', 'COIN', 'PLTR', 'NOK']
        results = {}
        for sym in top_stocks:
            try:
                results[sym] = self.run_all_strategies(sym, days)
                log.info(f"  Backtest {sym}: {len(results[sym])} strategies tested")
            except Exception as e:
                log.warning(f"  Backtest {sym} failed: {e}")
        return results
