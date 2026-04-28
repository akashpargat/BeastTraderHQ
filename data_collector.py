"""
Beast v2.0 — Data Collector
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Aggregates all market data from Alpaca with freshness TTLs.
This is the ONLY module that fetches raw market data.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockLatestQuoteRequest, StockSnapshotRequest,
    StockBarsRequest
)
from alpaca.data.timeframe import TimeFrame

from models import MarketData, Quote, Position, Regime

log = logging.getLogger('Beast.DataCollector')
ET = ZoneInfo("America/New_York")

# Freshness TTLs
PRICE_TTL = 10       # seconds
MARKET_TTL = 30      # seconds
EARNINGS_TTL = 3600  # 1 hour


class DataCollector:
    """Collects and caches market data with freshness tracking."""

    def __init__(self, api_key: str, secret_key: str):
        self.trading_client = TradingClient(api_key, secret_key, paper=True)
        self.data_client = StockHistoricalDataClient(api_key, secret_key)
        self._cache: dict[str, tuple[any, datetime]] = {}
        self._earnings_cache: dict[str, datetime] = {}

    def _is_fresh(self, key: str, ttl: int) -> bool:
        if key not in self._cache:
            return False
        _, ts = self._cache[key]
        return (datetime.now() - ts).total_seconds() <= ttl

    def _set_cache(self, key: str, value):
        self._cache[key] = (value, datetime.now())

    def _get_cache(self, key: str):
        if key in self._cache:
            return self._cache[key][0]
        return None

    # ── Market Status ──────────────────────────────────

    def is_market_open(self) -> bool:
        try:
            clock = self.trading_client.get_clock()
            return clock.is_open
        except Exception as e:
            log.error(f"Clock check failed: {e}")
            return False

    def get_next_open(self) -> Optional[datetime]:
        try:
            clock = self.trading_client.get_clock()
            return clock.next_open
        except:
            return None

    # ── Quotes ─────────────────────────────────────────

    def get_quote(self, symbol: str) -> Optional[Quote]:
        """Get latest quote with 10-second TTL."""
        cache_key = f"quote:{symbol}"
        if self._is_fresh(cache_key, PRICE_TTL):
            return self._get_cache(cache_key)

        try:
            req = StockLatestQuoteRequest(
                symbol_or_symbols=symbol, feed='iex'
            )
            raw = self.data_client.get_stock_latest_quote(req)
            if symbol in raw:
                q = raw[symbol]
                quote = Quote(
                    symbol=symbol,
                    bid=float(q.bid_price),
                    ask=float(q.ask_price),
                    last=float((q.bid_price + q.ask_price) / 2),
                    timestamp=datetime.now(),
                )
                self._set_cache(cache_key, quote)
                return quote
        except Exception as e:
            log.error(f"Quote fetch failed for {symbol}: {e}")
        return None

    def get_quotes_batch(self, symbols: list[str]) -> dict[str, Quote]:
        """Get quotes for multiple symbols at once."""
        results = {}
        try:
            req = StockLatestQuoteRequest(
                symbol_or_symbols=symbols, feed='iex'
            )
            raw = self.data_client.get_stock_latest_quote(req)
            for sym, q in raw.items():
                quote = Quote(
                    symbol=sym,
                    bid=float(q.bid_price),
                    ask=float(q.ask_price),
                    last=float((q.bid_price + q.ask_price) / 2),
                    timestamp=datetime.now(),
                )
                results[sym] = quote
                self._set_cache(f"quote:{sym}", quote)
        except Exception as e:
            log.error(f"Batch quote fetch failed: {e}")
        return results

    # ── Snapshots ──────────────────────────────────────

    def get_snapshot(self, symbol: str) -> Optional[dict]:
        """Get full snapshot (daily bar, prev bar, latest quote)."""
        cache_key = f"snap:{symbol}"
        if self._is_fresh(cache_key, MARKET_TTL):
            return self._get_cache(cache_key)

        try:
            req = StockSnapshotRequest(
                symbol_or_symbols=symbol, feed='iex'
            )
            raw = self.data_client.get_stock_snapshot(req)
            if symbol in raw:
                snap = raw[symbol]
                result = {
                    'symbol': symbol,
                    'price': float(snap.daily_bar.close) if snap.daily_bar else 0,
                    'open': float(snap.daily_bar.open) if snap.daily_bar else 0,
                    'high': float(snap.daily_bar.high) if snap.daily_bar else 0,
                    'low': float(snap.daily_bar.low) if snap.daily_bar else 0,
                    'volume': int(snap.daily_bar.volume) if snap.daily_bar else 0,
                    'prev_close': float(snap.previous_daily_bar.close) if snap.previous_daily_bar else 0,
                }
                if result['prev_close'] > 0:
                    result['change_pct'] = (result['price'] - result['prev_close']) / result['prev_close']
                else:
                    result['change_pct'] = 0
                self._set_cache(cache_key, result)
                return result
        except Exception as e:
            log.error(f"Snapshot fetch failed for {symbol}: {e}")
        return None

    # ── OHLCV Bars ─────────────────────────────────────

    def get_bars(self, symbol: str, timeframe: str = '5Min',
                 limit: int = 50) -> list[dict]:
        """Get historical bars for technical analysis."""
        try:
            end = datetime.now(ET)
            start = end - timedelta(days=5)

            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Minute,
                start=start,
                end=end,
                feed='iex',
            )
            raw = self.data_client.get_stock_bars(req)
            bars = []
            if symbol in raw:
                for b in raw[symbol]:
                    bars.append({
                        'time': b.timestamp,
                        'open': float(b.open),
                        'high': float(b.high),
                        'low': float(b.low),
                        'close': float(b.close),
                        'volume': int(b.volume),
                    })
            # Return last N bars
            return bars[-limit:] if len(bars) > limit else bars
        except Exception as e:
            log.error(f"Bars fetch failed for {symbol}: {e}")
            return []

    # ── Market Overview ────────────────────────────────

    def get_market_data(self, positions: list[Position]) -> MarketData:
        """Build a complete MarketData snapshot."""
        spy_snap = self.get_snapshot('SPY')
        qqq_snap = self.get_snapshot('QQQ')

        spy_change = spy_snap['change_pct'] if spy_snap else 0
        regime = self._detect_regime(spy_change)

        try:
            acct = self.trading_client.get_account()
            equity = float(acct.equity)
            buying_power = float(acct.buying_power)
            day_trades = int(acct.daytrade_count)
        except:
            equity = 0
            buying_power = 0
            day_trades = 0

        return MarketData(
            spy_price=spy_snap['price'] if spy_snap else 0,
            spy_change_pct=spy_change,
            qqq_price=qqq_snap['price'] if qqq_snap else 0,
            regime=regime,
            positions=positions,
            account_equity=equity,
            buying_power=buying_power,
            day_trade_count=day_trades,
            timestamp=datetime.now(),
        )

    def _detect_regime(self, spy_change_pct: float) -> Regime:
        """Detect regime with hysteresis (Fix 7 from rubber-duck)."""
        # Simple threshold for now — hysteresis added in regime_detector.py
        if spy_change_pct > 0.003:
            return Regime.BULL
        elif spy_change_pct < -0.01:
            return Regime.RED_ALERT
        elif spy_change_pct < -0.003:
            return Regime.BEAR
        else:
            return Regime.CHOPPY

    # ── Movers & Active ────────────────────────────────

    def get_movers(self) -> dict:
        """Get market movers from Alpaca."""
        # Note: alpaca-py doesn't have a direct movers endpoint in all versions.
        # This would use the REST API directly if needed.
        return {'gainers': [], 'losers': []}

    # ── Earnings Calendar ──────────────────────────────

    def get_earnings_dates(self, symbols: list[str]) -> dict[str, datetime]:
        """Get earnings dates. Cached for 1 hour."""
        if self._is_fresh("earnings_all", EARNINGS_TTL):
            return self._get_cache("earnings_all") or {}

        dates = {}
        try:
            import yfinance as yf
            for sym in symbols:
                try:
                    stock = yf.Ticker(sym)
                    info = stock.info
                    ts = info.get('earningsTimestamp')
                    if ts:
                        dates[sym] = datetime.fromtimestamp(ts)
                except:
                    pass
            self._set_cache("earnings_all", dates)
        except Exception as e:
            log.error(f"Earnings fetch failed: {e}")
        return dates
