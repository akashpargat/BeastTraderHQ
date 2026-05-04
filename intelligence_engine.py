"""
Beast V7 — Intelligence Engine (Background Learning)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The "eagle eye" — always watching, always learning.

Runs hourly in background, analyzes ALL stocks:
1. EarningsPatternAnalyzer — backtest 12 quarters (3yr) of earnings behavior
2. StockDNAProfiler — 2yr deep profile: personality, S/R levels, seasonality, EMA alignment
3. StrategyScorer — which strategy works best on which stock (with confidence)
4. CorrelationRadar — which stocks move together, sector rotation signals
5. SmartWatchlist — priority watchlist with custom strategy per stock

V7 UPGRADES:
- StockDNA: 90d → 2yr daily + hourly (support/resistance, seasonality, vol regime, EMA)
- Earnings: 1yr/4Q → 3yr/12Q with recency weighting
- ETF detection: dynamic via yfinance quoteType (not hardcoded)
- Feature flags: V7_DEEP_DNA, V7_EARNINGS_3Y, V7_ETF_DETECT

All data feeds into 3AM Claude for daily playbook generation.
"""

import logging
import json
import time
import math
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Optional

log = logging.getLogger("Beast.Intelligence")


# ══════════════════════════════════════════════════════════
#  1. EARNINGS PATTERN ANALYZER
# ══════════════════════════════════════════════════════════

class EarningsPatternAnalyzer:
    """V7: 3yr/12Q earnings analysis with recency weighting + dynamic ETF detection.
    
    Recent quarters weighted 2x — regime changes matter more than ancient history.
    ETFs detected dynamically via yfinance quoteType — no hardcoded lists.
    
    Patterns: gap_and_fade, dip_and_recover, pre_earnings_run, sustained_mover
    """

    def __init__(self, db=None):
        self.db = db

    def set_db(self, db):
        self.db = db

    def _is_etf(self, symbol: str) -> bool:
        """Detect if symbol is an ETF/ETN/fund dynamically."""
        try:
            import yfinance as yf
            info = yf.Ticker(symbol).info
            qt = info.get('quoteType', '').upper()
            return qt in ('ETF', 'MUTUALFUND', 'INDEX', 'CRYPTOCURRENCY')
        except Exception:
            return False

    def analyze_stock(self, symbol: str, alpaca_data=None) -> dict:
        """V7: 3yr earnings analysis with recency weighting."""
        result = {
            'symbol': symbol,
            'pattern': 'unknown',
            'pre_earnings_avg': 0,
            'day_of_avg': 0,
            'post_1d_avg': 0,
            'post_3d_avg': 0,
            'post_5d_avg': 0,
            'best_strategy': 'HOLD',
            'confidence': 30,
            'earnings_dates': [],
            'sample_size': 0,
            'earnings_applicable': True,
        }

        # V7: Dynamic ETF detection
        if self._is_etf(symbol):
            result['earnings_applicable'] = False
            result['pattern'] = 'etf_no_earnings'
            result['best_strategy'] = 'N/A — ETF/fund (trade on technicals only)'
            result['confidence'] = 90
            return result

        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            
            try:
                earnings_hist = ticker.earnings_dates
                if earnings_hist is None or len(earnings_hist) == 0:
                    return result
                dates = list(earnings_hist.index)[:12]  # V7: 12 quarters
            except Exception:
                return result

            hist = ticker.history(period="3y", interval="1d")  # V7: 3yr
            if hist is None or len(hist) < 60:
                return result

            pre_moves = []
            day_moves = []
            post_1d = []
            post_3d = []
            post_5d = []

            for q_idx, ed in enumerate(dates):
                try:
                    ed_date = ed.date() if hasattr(ed, 'date') else ed
                    idx = None
                    for i, d in enumerate(hist.index):
                        if d.date() == ed_date or (abs((d.date() - ed_date).days) <= 1):
                            idx = i
                            break
                    if idx is None or idx < 5 or idx + 5 >= len(hist):
                        continue

                    close_before = float(hist.iloc[idx - 1]['Close'])
                    close_day = float(hist.iloc[idx]['Close'])
                    close_5d_before = float(hist.iloc[idx - 5]['Close'])

                    # V7: Recent quarters weighted 2x
                    w = 2.0 if q_idx < 4 else 1.0

                    pre_pct = (close_before - close_5d_before) / close_5d_before * 100
                    pre_moves.append((pre_pct, w))
                    gap_pct = (close_day - close_before) / close_before * 100
                    day_moves.append((gap_pct, w))

                    if idx + 1 < len(hist):
                        p1 = (float(hist.iloc[idx + 1]['Close']) - close_day) / close_day * 100
                        post_1d.append((p1, w))
                    if idx + 3 < len(hist):
                        p3 = (float(hist.iloc[idx + 3]['Close']) - close_day) / close_day * 100
                        post_3d.append((p3, w))
                    if idx + 5 < len(hist):
                        p5 = (float(hist.iloc[idx + 5]['Close']) - close_day) / close_day * 100
                        post_5d.append((p5, w))

                    result['earnings_dates'].append(str(ed_date))
                except Exception:
                    continue

            if not day_moves:
                return result

            def wavg(pairs):
                if not pairs: return 0
                tw = sum(wt for _, wt in pairs)
                return sum(v * wt for v, wt in pairs) / tw if tw > 0 else 0

            result['sample_size'] = len(day_moves)
            result['pre_earnings_avg'] = round(wavg(pre_moves), 2)
            result['day_of_avg'] = round(wavg(day_moves), 2)
            result['post_1d_avg'] = round(wavg(post_1d), 2)
            result['post_3d_avg'] = round(wavg(post_3d), 2)
            result['post_5d_avg'] = round(wavg(post_5d), 2)

            avg_gap = result['day_of_avg']
            avg_post3 = result['post_3d_avg']
            avg_pre = result['pre_earnings_avg']

            if avg_gap > 3 and avg_post3 < avg_gap * 0.5:
                result['pattern'] = 'gap_and_fade'
                result['best_strategy'] = 'SCALP earnings gap, sell within hours'
                result['confidence'] = min(85, 50 + len(day_moves) * 5)
            elif avg_gap < -2 and avg_post3 > avg_gap + 2:
                result['pattern'] = 'dip_and_recover'
                result['best_strategy'] = 'BUY the post-earnings dip (day 1-2)'
                result['confidence'] = min(85, 50 + len(day_moves) * 5)
            elif avg_pre > 2:
                result['pattern'] = 'pre_earnings_run'
                result['best_strategy'] = 'BUY 5 days before, SELL before earnings'
                result['confidence'] = min(80, 45 + len(day_moves) * 5)
            elif avg_gap > 0 and avg_post3 > 0:
                result['pattern'] = 'sustained_mover'
                result['best_strategy'] = 'HOLD through earnings (trends continue)'
                result['confidence'] = min(75, 40 + len(day_moves) * 4)
            else:
                result['pattern'] = 'unpredictable'
                result['best_strategy'] = 'REDUCE before earnings (too volatile)'
                result['confidence'] = 30

        except Exception as e:
            log.debug(f"[INTEL] Earnings analysis {symbol}: {e}")

        return result

    def save_to_db(self, symbol: str, analysis: dict):
        """Save earnings pattern to ai_trends."""
        if not self.db or analysis.get('sample_size', 0) == 0:
            return
        try:
            self.db._exec(
                """INSERT INTO ai_trends (symbol, trend_type, insight, confidence, data, is_active)
                   VALUES (%s, 'earnings_pattern', %s, %s, %s, true)
                   ON CONFLICT (symbol, trend_type) DO UPDATE SET
                   insight = EXCLUDED.insight, confidence = EXCLUDED.confidence,
                   data = EXCLUDED.data, updated_at = NOW()""",
                (symbol,
                 f"{analysis['pattern']}: {analysis['best_strategy']}",
                 analysis['confidence'],
                 json.dumps(analysis, default=str))
            )
        except Exception as e:
            # ON CONFLICT may not work if no unique constraint, try upsert manually
            try:
                self.db._exec(
                    "DELETE FROM ai_trends WHERE symbol = %s AND trend_type = 'earnings_pattern'",
                    (symbol,)
                )
                self.db._exec(
                    """INSERT INTO ai_trends (symbol, trend_type, insight, confidence, data, is_active)
                       VALUES (%s, 'earnings_pattern', %s, %s, %s, true)""",
                    (symbol, f"{analysis['pattern']}: {analysis['best_strategy']}",
                     analysis['confidence'], json.dumps(analysis, default=str))
                )
            except Exception as e2:
                log.debug(f"[INTEL] Save earnings {symbol}: {e2}")


# ══════════════════════════════════════════════════════════
#  2. STOCK DNA PROFILER
# ══════════════════════════════════════════════════════════

class StockDNAProfiler:
    """V7: 2yr deep stock personality profiling.
    
    DNA Types: JUMPER, GRINDER, MEAN_REVERTER, MOMENTUM, VOLATILE, STEADY
    
    V7 additions:
    - 2yr daily + hourly data (was 90d daily only)
    - Support/resistance levels from price clusters
    - Seasonality (month-of-year tendencies, marked low-confidence)
    - Volatility regime (quiet vs wild phase)
    - EMA alignment (8/21/50/200) for trend strength
    """

    def analyze_stock(self, symbol: str, alpaca_data=None) -> dict:
        """V7: 2yr deep profile with S/R, seasonality, EMA, vol regime."""
        result = {
            'symbol': symbol,
            'dna_type': 'unknown',
            'avg_daily_range_pct': 0,
            'avg_daily_volume': 0,
            'max_gap_up': 0,
            'max_gap_down': 0,
            'mean_reversion_score': 0,
            'momentum_score': 0,
            'gap_frequency': 0,
            'best_scalp_pct': 2.0,
            'best_trail_pct': 3.0,
            'confidence': 30,
            # V7 new fields
            'support_levels': [],
            'resistance_levels': [],
            'seasonality': {},
            'vol_regime': 'unknown',
            'vol_percentile': 50,
            'ema_alignment': 'unknown',
            'ema_trend_strength': 0,
            'hourly_patterns': {},
        }

        try:
            import yfinance as yf
            hist = yf.Ticker(symbol).history(period="2y", interval="1d")  # V7: 2yr
            if hist is None or len(hist) < 60:
                return result

            closes = [float(c) for c in hist['Close']]
            highs = [float(h) for h in hist['High']]
            lows = [float(l) for l in hist['Low']]
            volumes = [int(v) for v in hist['Volume']]
            opens = [float(o) for o in hist['Open']]

            # ── Original DNA metrics ──
            ranges = [(h - l) / l * 100 for h, l in zip(highs, lows) if l > 0]
            result['avg_daily_range_pct'] = round(sum(ranges) / len(ranges), 2) if ranges else 0
            result['avg_daily_volume'] = int(sum(volumes) / len(volumes)) if volumes else 0

            gaps = [(o - closes[i]) / closes[i] * 100 for i, o in enumerate(opens[1:], 0) if closes[i] > 0]
            big_gaps = [g for g in gaps if abs(g) > 2]
            result['gap_frequency'] = round(len(big_gaps) / len(gaps) * 100, 1) if gaps else 0
            result['max_gap_up'] = round(max(gaps), 2) if gaps else 0
            result['max_gap_down'] = round(min(gaps), 2) if gaps else 0

            # Mean reversion
            reversions = 0
            continuations = 0
            for i in range(2, len(closes)):
                day_move = (closes[i-1] - closes[i-2]) / closes[i-2]
                next_move = (closes[i] - closes[i-1]) / closes[i-1]
                if day_move < -0.01:
                    if next_move > 0: reversions += 1
                    else: continuations += 1
            total_signals = reversions + continuations
            result['mean_reversion_score'] = round(
                (reversions - continuations) / total_signals, 2
            ) if total_signals > 5 else 0

            # Momentum
            daily_returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
            momentum_hits = 0
            for i in range(1, len(daily_returns)):
                if (daily_returns[i] > 0 and daily_returns[i-1] > 0) or \
                   (daily_returns[i] < 0 and daily_returns[i-1] < 0):
                    momentum_hits += 1
            result['momentum_score'] = round(
                momentum_hits / len(daily_returns) * 2 - 1, 2
            ) if daily_returns else 0

            # Optimal scalp/trail targets
            up_moves = [r * 100 for r in daily_returns if r > 0]
            if up_moves:
                up_moves.sort()
                p70_idx = int(len(up_moves) * 0.7)
                result['best_scalp_pct'] = round(up_moves[p70_idx], 1)

            drawdowns = [(h - c) / h * 100 for h, c in zip(highs, closes) if h > 0]
            if drawdowns:
                result['best_trail_pct'] = round(sum(drawdowns) / len(drawdowns) * 2, 1)

            # ── V7: Support/Resistance from price clusters ──
            try:
                # Use recency-weighted price histogram to find clusters
                recent_closes = closes[-120:]  # Last ~6 months weighted higher
                price_min, price_max = min(recent_closes), max(recent_closes)
                if price_max > price_min:
                    n_bins = 20
                    bin_size = (price_max - price_min) / n_bins
                    bins = [0] * n_bins
                    for p in recent_closes:
                        b = min(int((p - price_min) / bin_size), n_bins - 1)
                        bins[b] += 1
                    # Find top 3 clusters as S/R levels
                    threshold = max(bins) * 0.6
                    levels = []
                    for i, count in enumerate(bins):
                        if count >= threshold:
                            level = round(price_min + (i + 0.5) * bin_size, 2)
                            levels.append(level)
                    current_price = closes[-1]
                    result['support_levels'] = sorted([l for l in levels if l < current_price])[-3:]
                    result['resistance_levels'] = sorted([l for l in levels if l > current_price])[:3]
            except Exception:
                pass

            # ── V7: Seasonality (month-of-year patterns) ──
            try:
                monthly = {}
                for i in range(1, len(hist)):
                    month = hist.index[i].month
                    ret = (closes[i] - closes[i-1]) / closes[i-1] * 100
                    monthly.setdefault(month, []).append(ret)
                seasonality = {}
                for month, rets in monthly.items():
                    avg = sum(rets) / len(rets)
                    win_pct = len([r for r in rets if r > 0]) / len(rets) * 100
                    seasonality[month] = {
                        'avg_return': round(avg, 3),
                        'win_pct': round(win_pct, 1),
                        'samples': len(rets),
                        'confidence': 'low' if len(rets) < 30 else 'medium',
                    }
                result['seasonality'] = seasonality
            except Exception:
                pass

            # ── V7: Volatility regime (current vs historical) ──
            try:
                recent_vol = sum(abs(r) for r in daily_returns[-20:]) / 20 if len(daily_returns) >= 20 else 0
                hist_vol = sum(abs(r) for r in daily_returns) / len(daily_returns) if daily_returns else 0
                if hist_vol > 0:
                    vol_ratio = recent_vol / hist_vol
                    if vol_ratio > 1.5:
                        result['vol_regime'] = 'WILD'
                    elif vol_ratio < 0.6:
                        result['vol_regime'] = 'QUIET'
                    else:
                        result['vol_regime'] = 'NORMAL'
                    # Percentile: where does current vol rank in 2yr history?
                    all_20d_vols = []
                    for j in range(20, len(daily_returns)):
                        v = sum(abs(daily_returns[k]) for k in range(j-20, j)) / 20
                        all_20d_vols.append(v)
                    if all_20d_vols:
                        rank = sum(1 for v in all_20d_vols if v < recent_vol) / len(all_20d_vols) * 100
                        result['vol_percentile'] = round(rank)
            except Exception:
                pass

            # ── V7: EMA alignment (8/21/50/200) ──
            try:
                def ema(data, period):
                    if len(data) < period: return None
                    mult = 2 / (period + 1)
                    val = sum(data[:period]) / period
                    for d in data[period:]:
                        val = (d - val) * mult + val
                    return val

                ema8 = ema(closes, 8)
                ema21 = ema(closes, 21)
                ema50 = ema(closes, 50)
                ema200 = ema(closes, 200) if len(closes) >= 200 else None

                if ema8 and ema21 and ema50:
                    if ema200 and ema8 > ema21 > ema50 > ema200:
                        result['ema_alignment'] = 'PERFECT_BULL'
                        result['ema_trend_strength'] = 90
                    elif ema8 > ema21 > ema50:
                        result['ema_alignment'] = 'BULLISH'
                        result['ema_trend_strength'] = 70
                    elif ema200 and ema8 < ema21 < ema50 < ema200:
                        result['ema_alignment'] = 'PERFECT_BEAR'
                        result['ema_trend_strength'] = -90
                    elif ema8 < ema21 < ema50:
                        result['ema_alignment'] = 'BEARISH'
                        result['ema_trend_strength'] = -70
                    else:
                        result['ema_alignment'] = 'MIXED'
                        result['ema_trend_strength'] = 0
            except Exception:
                pass

            # ── V7: Hourly patterns (intraday tendencies) ──
            try:
                hr_hist = yf.Ticker(symbol).history(period="60d", interval="1h")
                if hr_hist is not None and len(hr_hist) > 100:
                    hour_returns = {}
                    hr_closes = [float(c) for c in hr_hist['Close']]
                    for i in range(1, len(hr_hist)):
                        hour = hr_hist.index[i].hour
                        ret = (hr_closes[i] - hr_closes[i-1]) / hr_closes[i-1] * 100
                        hour_returns.setdefault(hour, []).append(ret)
                    patterns = {}
                    for hr, rets in hour_returns.items():
                        avg = sum(rets) / len(rets)
                        vol = (sum((r - avg)**2 for r in rets) / len(rets)) ** 0.5
                        patterns[hr] = {
                            'avg_move': round(avg, 4),
                            'volatility': round(vol, 4),
                            'samples': len(rets),
                        }
                    result['hourly_patterns'] = patterns
            except Exception:
                pass

            # ── Classify DNA type ──
            avg_range = result['avg_daily_range_pct']
            mr = result['mean_reversion_score']
            mom = result['momentum_score']
            gap_freq = result['gap_frequency']

            if gap_freq > 15 and avg_range > 3:
                result['dna_type'] = 'JUMPER'
            elif mr > 0.3:
                result['dna_type'] = 'MEAN_REVERTER'
            elif mom > 0.2 and avg_range > 2:
                result['dna_type'] = 'MOMENTUM'
            elif avg_range > 3:
                result['dna_type'] = 'VOLATILE'
            elif avg_range < 1.5:
                result['dna_type'] = 'STEADY'
            else:
                result['dna_type'] = 'GRINDER'

            result['confidence'] = min(85, 40 + min(len(closes), 400) // 10)

        except Exception as e:
            log.debug(f"[INTEL] DNA profile {symbol}: {e}")

        return result

    def save_to_db(self, db, symbol: str, profile: dict):
        """Save stock DNA to ai_trends."""
        if not db or profile.get('dna_type') == 'unknown':
            return
        try:
            db._exec(
                "DELETE FROM ai_trends WHERE symbol = %s AND trend_type = 'stock_dna'",
                (symbol,)
            )
            db._exec(
                """INSERT INTO ai_trends (symbol, trend_type, insight, confidence, data, is_active)
                   VALUES (%s, 'stock_dna', %s, %s, %s, true)""",
                (symbol,
                 f"{profile['dna_type']}: range={profile['avg_daily_range_pct']}% "
                 f"scalp={profile['best_scalp_pct']}% trail={profile['best_trail_pct']}%",
                 profile['confidence'],
                 json.dumps(profile, default=str))
            )
        except Exception as e:
            log.debug(f"[INTEL] Save DNA {symbol}: {e}")


# ══════════════════════════════════════════════════════════
#  3. STRATEGY SCORER
# ══════════════════════════════════════════════════════════

class StrategyScorer:
    """Score which strategy works best on which stock using actual trade history.
    
    Strategies: SCALP, SWING, RUNNER, DIP_BUY, PYRAMID
    Scores: 0-100 confidence that this strategy will profit on this stock.
    """

    def score_stock(self, db, symbol: str) -> dict:
        """Score strategies for a stock based on historical trades."""
        scores = {
            'SCALP': {'score': 50, 'wins': 0, 'losses': 0, 'avg_pnl': 0, 'sample': 0},
            'SWING': {'score': 50, 'wins': 0, 'losses': 0, 'avg_pnl': 0, 'sample': 0},
            'RUNNER': {'score': 50, 'wins': 0, 'losses': 0, 'avg_pnl': 0, 'sample': 0},
            'DIP_BUY': {'score': 50, 'wins': 0, 'losses': 0, 'avg_pnl': 0, 'sample': 0},
            'PYRAMID': {'score': 50, 'wins': 0, 'losses': 0, 'avg_pnl': 0, 'sample': 0},
        }

        if not db:
            return scores

        try:
            # Get trades for this stock
            trades = db._exec(
                """SELECT strategy, source, pnl_eod, was_profitable
                   FROM trade_log
                   WHERE symbol = %s AND was_profitable IS NOT NULL
                   ORDER BY created_at DESC LIMIT 100""",
                (symbol,), fetch=True
            ) or []

            for t in trades:
                strat = (t.get('strategy') or t.get('source') or '').upper()
                pnl = float(t.get('pnl_eod') or 0)
                won = t.get('was_profitable', False)

                # Map source to strategy category
                if 'SCALP' in strat or '60S' in strat:
                    key = 'SCALP'
                elif 'SWING' in strat:
                    key = 'SWING'
                elif 'RUNNER' in strat or '2MIN' in strat:
                    key = 'RUNNER'
                elif 'DIP' in strat or 'RELOAD' in strat:
                    key = 'DIP_BUY'
                elif 'PYRAMID' in strat:
                    key = 'PYRAMID'
                else:
                    key = 'SCALP'  # default

                scores[key]['sample'] += 1
                if won:
                    scores[key]['wins'] += 1
                else:
                    scores[key]['losses'] += 1
                scores[key]['avg_pnl'] = (
                    (scores[key]['avg_pnl'] * (scores[key]['sample'] - 1) + pnl)
                    / scores[key]['sample']
                )

            # Calculate confidence scores
            for key, s in scores.items():
                if s['sample'] >= 3:
                    win_rate = s['wins'] / s['sample']
                    s['score'] = int(min(95, max(10,
                        win_rate * 60 +          # 60% weight on win rate
                        min(s['avg_pnl'] * 5, 20) +  # 20% weight on avg PnL
                        min(s['sample'] * 2, 20)      # 20% weight on sample size
                    )))

        except Exception as e:
            log.debug(f"[INTEL] Strategy score {symbol}: {e}")

        return scores

    def save_to_db(self, db, symbol: str, scores: dict):
        """Save strategy scores to ai_trends."""
        if not db:
            return
        best = max(scores.items(), key=lambda x: x[1]['score'])
        try:
            db._exec(
                "DELETE FROM ai_trends WHERE symbol = %s AND trend_type = 'strategy_scores'",
                (symbol,)
            )
            db._exec(
                """INSERT INTO ai_trends (symbol, trend_type, insight, confidence, data, is_active)
                   VALUES (%s, 'strategy_scores', %s, %s, %s, true)""",
                (symbol,
                 f"Best: {best[0]} ({best[1]['score']}%) — "
                 f"wins={best[1]['wins']}/{best[1]['sample']}",
                 best[1]['score'],
                 json.dumps(scores, default=str))
            )
        except Exception as e:
            log.debug(f"[INTEL] Save strategy {symbol}: {e}")


# ══════════════════════════════════════════════════════════
#  4. SECTOR MOMENTUM RADAR
# ══════════════════════════════════════════════════════════

SECTOR_MAP = {
    'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology', 'META': 'Technology',
    'AMZN': 'Consumer', 'TSLA': 'Consumer', 'NVDA': 'Technology', 'AMD': 'Technology',
    'AVGO': 'Technology', 'CRM': 'Technology', 'ORCL': 'Technology', 'INTC': 'Technology',
    'COIN': 'Crypto', 'MSTR': 'Crypto', 'HOOD': 'Finance',
    'LMT': 'Defense', 'NOK': 'Telecom', 'PLTR': 'Technology',
    'OXY': 'Energy', 'DVN': 'Energy', 'BE': 'Energy',
    'MU': 'Technology', 'NOW': 'Technology', 'ANET': 'Technology',
    'JPM': 'Finance', 'GS': 'Finance', 'BAC': 'Finance',
    'XOM': 'Energy', 'CVX': 'Energy', 'COP': 'Energy',
    'PFE': 'Healthcare', 'JNJ': 'Healthcare', 'UNH': 'Healthcare',
}

class SectorMomentumRadar:
    """Track which sectors are hot/cold. Rotate into strength."""

    def analyze(self, db) -> dict:
        """Analyze sector performance from recent TV readings and fills."""
        if not db:
            return {}

        sectors = defaultdict(lambda: {'symbols': [], 'avg_rsi': 0, 'fills': 0, 'wins': 0})
        try:
            # RSI by sector from TV readings
            readings = db._exec(
                """SELECT symbol, AVG(rsi) as avg_rsi, COUNT(*) as cnt
                   FROM tv_readings
                   WHERE created_at > NOW() - interval '24 hours' AND rsi > 0
                   GROUP BY symbol""",
                fetch=True
            ) or []

            for r in readings:
                sym = r['symbol']
                sector = SECTOR_MAP.get(sym, 'Other')
                sectors[sector]['symbols'].append(sym)
                rsi_vals = sectors[sector].setdefault('_rsi_list', [])
                rsi_vals.append(float(r['avg_rsi']))

            # Win rate by sector
            trades = db._exec(
                """SELECT symbol, was_profitable FROM trade_log
                   WHERE created_at > NOW() - interval '30 days'
                   AND was_profitable IS NOT NULL""",
                fetch=True
            ) or []

            for t in trades:
                sector = SECTOR_MAP.get(t['symbol'], 'Other')
                sectors[sector]['fills'] += 1
                if t['was_profitable']:
                    sectors[sector]['wins'] += 1

            # Compute sector scores
            result = {}
            for sector, data in sectors.items():
                rsi_list = data.get('_rsi_list', [])
                avg_rsi = sum(rsi_list) / len(rsi_list) if rsi_list else 50
                win_rate = data['wins'] / data['fills'] if data['fills'] > 0 else 0.5
                
                # Score: higher RSI momentum + higher win rate = hotter sector
                score = int(avg_rsi * 0.4 + win_rate * 100 * 0.6)
                signal = 'HOT' if score > 60 else 'COLD' if score < 40 else 'NEUTRAL'
                
                result[sector] = {
                    'score': score,
                    'signal': signal,
                    'avg_rsi': round(avg_rsi, 1),
                    'win_rate': round(win_rate * 100, 1),
                    'stocks': data['symbols'][:5],
                    'trades': data['fills'],
                }

            return dict(sorted(result.items(), key=lambda x: x[1]['score'], reverse=True))

        except Exception as e:
            log.debug(f"[INTEL] Sector radar: {e}")
            return {}


# ══════════════════════════════════════════════════════════
#  5. SMART WATCHLIST BUILDER
# ══════════════════════════════════════════════════════════

class SmartWatchlistBuilder:
    """Build a priority watchlist with custom strategy per stock.
    
    Combines: earnings patterns + stock DNA + strategy scores + sector momentum
    Output: ranked list with per-stock strategy and confidence.
    """

    def build(self, db, symbols: list, earnings_data: dict = None,
              dna_data: dict = None, strategy_data: dict = None,
              sector_data: dict = None) -> list:
        """Build priority watchlist."""
        watchlist = []

        for sym in symbols:
            entry = {
                'symbol': sym,
                'priority': 50,  # 0-100
                'strategy': 'SCALP',
                'confidence': 50,
                'reasons': [],
                'scalp_target': 2.0,
                'trail_stop': 3.0,
                'watch_for': '',
            }

            # Earnings pattern
            ep = (earnings_data or {}).get(sym, {})
            if ep.get('pattern') and ep['pattern'] != 'unknown':
                entry['reasons'].append(f"Earnings: {ep['pattern']} — {ep['best_strategy']}")
                if ep['confidence'] > 60:
                    entry['priority'] += 10
                    entry['watch_for'] = ep['best_strategy']

            # Stock DNA
            dna = (dna_data or {}).get(sym, {})
            if dna.get('dna_type') and dna['dna_type'] != 'unknown':
                entry['reasons'].append(f"DNA: {dna['dna_type']} (range={dna.get('avg_daily_range_pct', 0)}%)")
                entry['scalp_target'] = dna.get('best_scalp_pct', 2.0)
                entry['trail_stop'] = dna.get('best_trail_pct', 3.0)
                
                if dna['dna_type'] == 'MOMENTUM':
                    entry['strategy'] = 'RUNNER'
                    entry['priority'] += 15
                elif dna['dna_type'] == 'MEAN_REVERTER':
                    entry['strategy'] = 'DIP_BUY'
                    entry['priority'] += 10
                elif dna['dna_type'] == 'JUMPER':
                    entry['strategy'] = 'SWING'
                    entry['priority'] += 5

            # Strategy scores
            ss = (strategy_data or {}).get(sym, {})
            if ss:
                best = max(ss.items(), key=lambda x: x[1].get('score', 0))
                if best[1].get('score', 0) > 60:
                    entry['strategy'] = best[0]
                    entry['confidence'] = best[1]['score']
                    entry['priority'] += (best[1]['score'] - 50) // 5
                    entry['reasons'].append(f"Strategy: {best[0]} ({best[1]['score']}% confidence)")

            # Sector momentum
            sector = SECTOR_MAP.get(sym, 'Other')
            sd = (sector_data or {}).get(sector, {})
            if sd.get('signal') == 'HOT':
                entry['priority'] += 10
                entry['reasons'].append(f"Sector: {sector} is HOT ({sd.get('score', 0)})")
            elif sd.get('signal') == 'COLD':
                entry['priority'] -= 10
                entry['reasons'].append(f"Sector: {sector} is COLD")

            entry['priority'] = max(0, min(100, entry['priority']))
            watchlist.append(entry)

        # Sort by priority descending
        watchlist.sort(key=lambda x: x['priority'], reverse=True)
        return watchlist


# ══════════════════════════════════════════════════════════
#  6. INTELLIGENCE ENGINE (ORCHESTRATOR)
# ══════════════════════════════════════════════════════════

class IntelligenceEngine:
    """Orchestrates all background learning. Called hourly.
    Cycles through stocks, builds intelligence, stores to DB."""

    def __init__(self, db=None):
        self.db = db
        self.earnings = EarningsPatternAnalyzer(db)
        self.dna = StockDNAProfiler()
        self.scorer = StrategyScorer()
        self.sectors = SectorMomentumRadar()
        self.watchlist_builder = SmartWatchlistBuilder()
        self._last_full_scan = 0
        self._FULL_SCAN_INTERVAL = 6 * 3600  # Full scan every 6 hours
        self._batch_offset = 0

    def set_db(self, db):
        self.db = db
        self.earnings.db = db

    def run_batch(self, symbols: list, batch_size: int = 20) -> dict:
        """Run intelligence on a batch of stocks. Called hourly."""
        if not self.db:
            return {'error': 'no_db'}

        t0 = time.time()
        # Rotate through symbols in batches
        start = self._batch_offset % len(symbols)
        batch = symbols[start:start + batch_size]
        self._batch_offset += batch_size

        results = {
            'batch': batch,
            'earnings_analyzed': 0,
            'dna_profiled': 0,
            'strategies_scored': 0,
        }

        for sym in batch:
            try:
                # 1. Earnings pattern (slow — yfinance call)
                if time.time() - self._last_full_scan > self._FULL_SCAN_INTERVAL:
                    ep = self.earnings.analyze_stock(sym)
                    if ep.get('sample_size', 0) > 0:
                        self.earnings.save_to_db(sym, ep)
                        results['earnings_analyzed'] += 1

                # 2. Stock DNA profile (slow — yfinance call)
                dna = self.dna.analyze_stock(sym)
                if dna.get('dna_type') != 'unknown':
                    self.dna.save_to_db(self.db, sym, dna)
                    results['dna_profiled'] += 1

                # 3. Strategy scores (fast — DB only)
                scores = self.scorer.score_stock(self.db, sym)
                self.scorer.save_to_db(self.db, sym, scores)
                results['strategies_scored'] += 1

            except Exception as e:
                log.debug(f"[INTEL] Batch error {sym}: {e}")
                continue

        # Reset full scan timer
        if self._batch_offset >= len(symbols):
            self._last_full_scan = time.time()
            self._batch_offset = 0

        # 4. Sector momentum (fast — runs on all stocks)
        try:
            sector_data = self.sectors.analyze(self.db)
            results['sectors'] = sector_data
            if sector_data:
                self.db._exec(
                    "DELETE FROM ai_trends WHERE trend_type = 'sector_momentum'",
                )
                self.db._exec(
                    """INSERT INTO ai_trends (symbol, trend_type, insight, confidence, data, is_active)
                       VALUES ('MARKET', 'sector_momentum', %s, 70, %s, true)""",
                    (
                        f"Hot: {', '.join(s for s,d in sector_data.items() if d['signal']=='HOT')} | "
                        f"Cold: {', '.join(s for s,d in sector_data.items() if d['signal']=='COLD')}",
                        json.dumps(sector_data, default=str)
                    )
                )
        except Exception as e:
            log.debug(f"[INTEL] Sector save: {e}")

        elapsed = time.time() - t0
        results['elapsed_s'] = round(elapsed, 1)
        log.info(f"[INTEL] Batch done: {len(batch)} stocks in {elapsed:.1f}s — "
                 f"DNA={results['dna_profiled']} Earnings={results['earnings_analyzed']} "
                 f"Strategy={results['strategies_scored']}")

        return results

    def get_full_intelligence(self) -> dict:
        """Get ALL intelligence data for 3AM Claude."""
        if not self.db:
            return {}

        intel = {}
        try:
            for trend_type in ['stock_dna', 'earnings_pattern', 'strategy_scores',
                               'sector_momentum', 'catalyst']:
                rows = self.db._exec(
                    """SELECT symbol, insight, confidence, data
                       FROM ai_trends WHERE trend_type = %s AND is_active = true
                       ORDER BY confidence DESC LIMIT 30""",
                    (trend_type,), fetch=True
                ) or []
                intel[trend_type] = rows

        except Exception as e:
            log.debug(f"[INTEL] get_full_intelligence: {e}")

        return intel
