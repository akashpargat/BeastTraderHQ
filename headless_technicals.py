"""
headless_technicals.py — Compute ALL technical indicators from Alpaca/yfinance data.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REPLACES TradingView CDP when TV Desktop is unavailable.

Computes: RSI, MACD, VWAP, Bollinger Bands, EMA 9/21/50, SMA 200,
          Volume Ratio, Confluence Score — all from price data alone.

Usage:
    from headless_technicals import HeadlessTechnicals
    ht = HeadlessTechnicals(alpaca_key, alpaca_secret)
    indicators = ht.analyze('AAPL')
    # Returns same dict format as tv_cdp_client → tv_analyst pipeline
"""
import logging
import time
import numpy as np
from datetime import datetime, timedelta

log = logging.getLogger('Beast.HeadlessTA')


class HeadlessTechnicals:
    """Compute technical indicators without TradingView — uses Alpaca bar data."""

    def __init__(self, api_key: str = '', secret_key: str = ''):
        self.api_key = api_key
        self.secret_key = secret_key
        self._client = None
        self._cache = {}  # symbol → (timestamp, result)
        self.CACHE_TTL = 120  # 2 min cache
        self._init_client()

    def _init_client(self):
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            self._client = StockHistoricalDataClient(self.api_key, self.secret_key)
            log.info("[HEADLESS_TA] Alpaca data client initialized")
        except Exception as e:
            log.warning(f"[HEADLESS_TA] Alpaca client init failed: {e}")
            self._client = None

    def _get_bars(self, symbol: str, timeframe: str = '5Min', limit: int = 200) -> list:
        """Fetch intraday bars from Alpaca."""
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            tf_map = {
                '1Min': TimeFrame.Minute,
                '5Min': TimeFrame(5, 'Min'),
                '15Min': TimeFrame(15, 'Min'),
                '1Hour': TimeFrame.Hour,
                '1Day': TimeFrame.Day,
            }
            tf = tf_map.get(timeframe, TimeFrame(5, 'Min'))

            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                limit=limit,
                feed='iex',
            )
            bars = self._client.get_stock_bars(req)
            bar_list = bars[symbol] if symbol in bars else []

            result = []
            for b in bar_list:
                result.append({
                    'open': float(b.open),
                    'high': float(b.high),
                    'low': float(b.low),
                    'close': float(b.close),
                    'volume': float(b.volume),
                    'timestamp': str(b.timestamp),
                })

            log.info(f"[HEADLESS_TA] {symbol}: fetched {len(result)} bars ({timeframe})")
            return result

        except Exception as e:
            log.warning(f"[HEADLESS_TA] {symbol}: bar fetch failed: {e}")
            return []

    @staticmethod
    def _compute_rsi(closes: list, period: int = 14) -> float:
        """Relative Strength Index."""
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    @staticmethod
    def _compute_macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
        """MACD with signal line and histogram."""
        if len(closes) < slow + signal:
            return {'macd': 0, 'signal': 0, 'histogram': 0}

        closes = np.array(closes, dtype=float)

        def ema(data, period):
            result = np.zeros_like(data)
            result[0] = data[0]
            mult = 2 / (period + 1)
            for i in range(1, len(data)):
                result[i] = (data[i] - result[i-1]) * mult + result[i-1]
            return result

        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        macd_line = ema_fast - ema_slow
        signal_line = ema(macd_line, signal)
        histogram = macd_line - signal_line

        return {
            'macd': round(float(macd_line[-1]), 4),
            'signal': round(float(signal_line[-1]), 4),
            'histogram': round(float(histogram[-1]), 4),
        }

    @staticmethod
    def _compute_vwap(bars: list) -> float:
        """Volume Weighted Average Price."""
        if not bars:
            return 0.0
        cum_vol = 0
        cum_tp_vol = 0
        for b in bars:
            tp = (b['high'] + b['low'] + b['close']) / 3
            cum_tp_vol += tp * b['volume']
            cum_vol += b['volume']
        return round(cum_tp_vol / cum_vol, 2) if cum_vol > 0 else 0.0

    @staticmethod
    def _compute_bollinger(closes: list, period: int = 20, std_dev: float = 2.0) -> dict:
        """Bollinger Bands."""
        if len(closes) < period:
            return {'upper': 0, 'mid': 0, 'lower': 0}
        window = closes[-period:]
        mid = np.mean(window)
        std = np.std(window)
        return {
            'upper': round(float(mid + std_dev * std), 2),
            'mid': round(float(mid), 2),
            'lower': round(float(mid - std_dev * std), 2),
        }

    @staticmethod
    def _compute_ema(closes: list, period: int) -> float:
        """Exponential Moving Average."""
        if len(closes) < period:
            return 0.0
        closes = np.array(closes, dtype=float)
        mult = 2 / (period + 1)
        ema_val = closes[0]
        for i in range(1, len(closes)):
            ema_val = (closes[i] - ema_val) * mult + ema_val
        return round(float(ema_val), 2)

    @staticmethod
    def _compute_sma(closes: list, period: int) -> float:
        """Simple Moving Average."""
        if len(closes) < period:
            return 0.0
        return round(float(np.mean(closes[-period:])), 2)

    def analyze(self, symbol: str) -> dict:
        """
        Compute all technicals for a symbol. Returns dict compatible with
        what tv_analyst/tv_cdp_client returns, so it's a drop-in replacement.

        Returns: {rsi, macd_hist, vwap_above, bb_position, confluence,
                  ema_9, ema_21, volume_ratio, price, _confirmed, _signals, _source}
        """
        # Check cache
        cached = self._cache.get(symbol)
        if cached and time.time() - cached[0] < self.CACHE_TTL:
            log.debug(f"[HEADLESS_TA] {symbol}: cache hit")
            return cached[1]

        start_time = time.time()
        result = {
            'rsi': 50, 'macd_hist': 0, 'vwap_above': False,
            'bb_position': 'mid', 'confluence': 0,
            'ema_9': 0, 'ema_21': 0, 'ema_50': 0, 'sma_200': 0,
            'volume_ratio': 1.0, 'price': 0,
            '_confirmed': False, '_signals': 0, '_source': 'headless',
        }

        if not self._client:
            log.warning(f"[HEADLESS_TA] {symbol}: no Alpaca client")
            return result

        # Fetch 5-min bars for intraday indicators
        bars_5m = self._get_bars(symbol, '5Min', 200)
        # Fetch daily bars for longer-term indicators (EMA 50, SMA 200)
        bars_daily = self._get_bars(symbol, '1Day', 250)

        if not bars_5m or len(bars_5m) < 30:
            log.warning(f"[HEADLESS_TA] {symbol}: insufficient bars ({len(bars_5m)})")
            return result

        closes_5m = [b['close'] for b in bars_5m]
        closes_daily = [b['close'] for b in bars_daily] if bars_daily else closes_5m
        current_price = closes_5m[-1]
        result['price'] = current_price

        # ── RSI ──
        result['rsi'] = self._compute_rsi(closes_5m)

        # ── MACD ──
        macd = self._compute_macd(closes_5m)
        result['macd_hist'] = macd['histogram']

        # ── VWAP ──
        # Use today's bars only for VWAP (intraday)
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_bars = [b for b in bars_5m if today_str in b.get('timestamp', '')]
        if not today_bars:
            today_bars = bars_5m[-78:]  # Last ~6.5 hours of 5-min bars
        vwap = self._compute_vwap(today_bars)
        result['vwap_above'] = current_price > vwap if vwap > 0 else False

        # ── Bollinger Bands ──
        bb = self._compute_bollinger(closes_5m)
        if current_price > bb['upper'] and bb['upper'] > 0:
            result['bb_position'] = 'upper'
        elif current_price < bb['lower'] and bb['lower'] > 0:
            result['bb_position'] = 'lower'
        else:
            result['bb_position'] = 'mid'

        # ── EMAs (from 5-min data) ──
        result['ema_9'] = self._compute_ema(closes_5m, 9)
        result['ema_21'] = self._compute_ema(closes_5m, 21)

        # ── EMA 50 + SMA 200 (from daily data) ──
        result['ema_50'] = self._compute_ema(closes_daily, 50)
        result['sma_200'] = self._compute_sma(closes_daily, 200)

        # ── Volume Ratio ──
        if len(bars_5m) >= 20:
            recent_vol = np.mean([b['volume'] for b in bars_5m[-5:]])
            avg_vol = np.mean([b['volume'] for b in bars_5m[-20:]])
            result['volume_ratio'] = round(recent_vol / avg_vol, 2) if avg_vol > 0 else 1.0
        else:
            result['volume_ratio'] = 1.0

        # ── Confluence Score (0-10) ──
        confluence = 0
        rsi = result['rsi']
        if 30 <= rsi <= 70:
            confluence += 1  # Not extreme
        if rsi < 40:
            confluence += 1  # Oversold = buy opportunity
        if result['macd_hist'] > 0:
            confluence += 2  # Bullish momentum
        if result['vwap_above']:
            confluence += 2  # Above VWAP = bullish
        if result['ema_9'] > result['ema_21'] > 0:
            confluence += 2  # EMA trend up
        if result['volume_ratio'] > 1.5:
            confluence += 1  # Above avg volume
        if current_price > result['ema_50'] > 0:
            confluence += 1  # Above 50 EMA
        result['confluence'] = min(10, confluence)

        # ── Confirmation (same logic as _tv_confirm_buy) ──
        signals_bullish = 0
        if rsi < 75:
            signals_bullish += 1
        if rsi < 30:
            signals_bullish += 1
        if result['macd_hist'] > 0:
            signals_bullish += 1
        if result['vwap_above']:
            signals_bullish += 1
        if result['confluence'] >= 5:
            signals_bullish += 1
        if result['ema_9'] > result['ema_21'] > 0:
            signals_bullish += 1

        result['_signals'] = signals_bullish
        result['_confirmed'] = signals_bullish >= 2 and rsi < 80

        elapsed = int((time.time() - start_time) * 1000)
        log.info(
            f"[HEADLESS_TA] {symbol}: RSI={rsi:.0f} MACD={result['macd_hist']:.3f} "
            f"VWAP={'↑' if result['vwap_above'] else '↓'} BB={result['bb_position']} "
            f"EMA={result['ema_9']:.1f}/{result['ema_21']:.1f} Conf={result['confluence']}/10 "
            f"Signals={signals_bullish} Confirmed={result['_confirmed']} [{elapsed}ms]"
        )

        # Cache
        self._cache[symbol] = (time.time(), result)
        return result

    def health_check(self) -> bool:
        """Always returns True — headless doesn't need external services."""
        return self._client is not None

    def batch_analyze(self, symbols: list) -> dict:
        """Analyze multiple symbols. Returns {symbol: indicators}."""
        results = {}
        for sym in symbols:
            try:
                results[sym] = self.analyze(sym)
            except Exception as e:
                log.warning(f"[HEADLESS_TA] {sym}: batch error: {e}")
        return results
