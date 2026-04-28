"""
Beast v2.0 — Technical Analyst
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pure math. No AI. No API calls. Takes price data, returns signals.
All indicators calculated locally from OHLCV bars.
"""
import logging
import numpy as np
from datetime import datetime
from models import TechnicalSignals

log = logging.getLogger('Beast.TechnicalAnalyst')


class TechnicalAnalyst:
    """Pure-math technical analysis engine."""

    def analyze(self, symbol: str, bars: list[dict], current_price: float = 0) -> TechnicalSignals:
        """Run full technical analysis on a stock's bars."""
        if len(bars) < 26:
            log.warning(f"{symbol}: Not enough bars ({len(bars)}) for full analysis")
            return TechnicalSignals(symbol=symbol)

        closes = [b['close'] for b in bars]
        highs = [b['high'] for b in bars]
        lows = [b['low'] for b in bars]
        volumes = [b['volume'] for b in bars]

        price = current_price or closes[-1]

        rsi = self._rsi(closes)
        macd, macd_signal, macd_hist = self._macd(closes)
        bb_upper, bb_mid, bb_lower = self._bollinger(closes)
        ema_9 = self._ema(closes, 9)
        ema_21 = self._ema(closes, 21)
        sma_20 = self._sma(closes, 20)
        sma_200 = self._sma(closes, 200) if len(closes) >= 200 else 0
        vwap = self._vwap(bars)
        vol_ratio = self._volume_ratio(volumes)
        orb_high, orb_low = self._orb(bars)

        confluence = self._confluence_score(
            price, orb_high, vwap, sma_200, macd_hist,
            rsi, vol_ratio, closes
        )

        return TechnicalSignals(
            symbol=symbol,
            rsi=rsi,
            macd=macd,
            macd_histogram=macd_hist,
            macd_signal=macd_signal,
            vwap=vwap,
            price_vs_vwap=price - vwap if vwap > 0 else 0,
            bb_upper=bb_upper,
            bb_mid=bb_mid,
            bb_lower=bb_lower,
            ema_9=ema_9,
            ema_21=ema_21,
            sma_20=sma_20,
            sma_200=sma_200,
            volume_ratio=vol_ratio,
            orb_high=orb_high,
            orb_low=orb_low,
            confluence_score=confluence,
            timestamp=datetime.now(),
        )

    # ── Indicators ─────────────────────────────────────

    def _rsi(self, closes: list, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def _macd(self, closes: list) -> tuple[float, float, float]:
        if len(closes) < 26:
            return 0, 0, 0
        arr = np.array(closes, dtype=float)
        ema12 = self._ema_arr(arr, 12)
        ema26 = self._ema_arr(arr, 26)
        macd_line = ema12[-1] - ema26[-1]

        macd_series = ema12 - ema26
        signal = self._ema_arr(macd_series[-9:], 9)[-1] if len(macd_series) >= 9 else macd_line
        histogram = macd_line - signal
        return round(macd_line, 4), round(signal, 4), round(histogram, 4)

    def _bollinger(self, closes: list, period: int = 20, std_dev: int = 2) -> tuple[float, float, float]:
        if len(closes) < period:
            return 0, 0, 0
        arr = np.array(closes[-period:])
        mid = float(np.mean(arr))
        std = float(np.std(arr))
        return round(mid + std_dev * std, 2), round(mid, 2), round(mid - std_dev * std, 2)

    def _ema(self, closes: list, period: int) -> float:
        if len(closes) < period:
            return closes[-1] if closes else 0
        return round(float(self._ema_arr(np.array(closes, dtype=float), period)[-1]), 2)

    def _ema_arr(self, arr: np.ndarray, period: int) -> np.ndarray:
        alpha = 2 / (period + 1)
        result = np.empty_like(arr)
        result[0] = arr[0]
        for i in range(1, len(arr)):
            result[i] = alpha * arr[i] + (1 - alpha) * result[i - 1]
        return result

    def _sma(self, closes: list, period: int) -> float:
        if len(closes) < period:
            return 0
        return round(float(np.mean(closes[-period:])), 2)

    def _vwap(self, bars: list) -> float:
        """Calculate VWAP from today's bars only."""
        if not bars:
            return 0
        total_pv = 0
        total_vol = 0
        for b in bars:
            typical = (b['high'] + b['low'] + b['close']) / 3
            vol = b['volume']
            total_pv += typical * vol
            total_vol += vol
        return round(total_pv / total_vol, 2) if total_vol > 0 else 0

    def _volume_ratio(self, volumes: list, period: int = 20) -> float:
        if len(volumes) < period + 1:
            return 1.0
        avg = np.mean(volumes[-period - 1:-1])
        current = volumes[-1]
        return round(current / avg, 2) if avg > 0 else 1.0

    def _orb(self, bars: list) -> tuple[float, float]:
        """Opening Range Breakout: first 3 bars (15 min on 5-min chart)."""
        if len(bars) < 3:
            return 0, 0
        orb_bars = bars[:3]
        high = max(b['high'] for b in orb_bars)
        low = min(b['low'] for b in orb_bars)
        return high, low

    # ── Confluence Scoring ─────────────────────────────

    def _confluence_score(self, price, orb_high, vwap, sma_200,
                          macd_hist, rsi, vol_ratio, closes) -> int:
        """Score 0-10 for ORB breakout confluence."""
        score = 0
        if orb_high > 0 and price > orb_high:
            score += 2  # ORB breakout
        if vwap > 0 and price > vwap:
            score += 2  # Above VWAP
        if sma_200 > 0 and price > sma_200:
            score += 1  # Above 200 SMA
        if macd_hist > 0:
            score += 1  # MACD positive
        if 40 <= rsi <= 70:
            score += 1  # RSI in sweet spot
        if vol_ratio > 1.2:
            score += 1  # Volume above average
        if len(closes) >= 2 and closes[-1] > closes[-2]:
            score += 1  # Above yesterday close
        # Break + retest pattern (price near ORB high)
        if orb_high > 0 and 0 < (price - orb_high) / orb_high < 0.005:
            score += 1
        return score
