"""
Beast v2.0 — Confidence Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Multi-strategy scoring across all 11 strategies (A-K).
Combines technicals, sentiment, and strategy-specific signals
into a single confidence score per stock.
"""
import logging
from datetime import datetime
from models import (
    ConfidenceResult, StrategyScore, SignalType, Strategy,
    TechnicalSignals, SentimentScore, Regime
)

log = logging.getLogger('Beast.ConfidenceEngine')

# Strategy weights by regime
REGIME_STRATEGY_MAP = {
    Regime.BULL: [
        Strategy.ORB_BREAKOUT, Strategy.GAP_AND_GO, Strategy.FAIR_VALUE_GAP,
        Strategy.BLUE_CHIP_REVERSION, Strategy.SMA_TREND_FOLLOW,
    ],
    Regime.BEAR: [
        Strategy.QUICK_FLIP, Strategy.TOUCH_AND_TURN, Strategy.RED_TO_GREEN,
        Strategy.BLUE_CHIP_REVERSION,
    ],
    Regime.CHOPPY: [
        Strategy.ORB_BREAKOUT, Strategy.GAP_AND_GO, Strategy.RED_TO_GREEN,
    ],
    Regime.RED_ALERT: [],  # No new entries
}

# Strategies that are TOXIC in certain regimes (backtested losses)
TOXIC_COMBOS = {
    Regime.CHOPPY: {Strategy.QUICK_FLIP, Strategy.TOUCH_AND_TURN},
    Regime.BEAR: {Strategy.ORB_BREAKOUT, Strategy.GAP_AND_GO},
    Regime.RED_ALERT: {Strategy.ORB_BREAKOUT, Strategy.GAP_AND_GO,
                       Strategy.VWAP_BOUNCE, Strategy.FAIR_VALUE_GAP},
}

# Component weights for final score
WEIGHTS = {
    'technical': 0.25,
    'sentiment': 0.15,
    'strategy_fit': 0.20,
    'momentum': 0.15,
    'analyst': 0.10,
    'volume': 0.10,
    'regime_bonus': 0.05,
}


class ConfidenceEngine:
    """Scores stocks across all strategies and produces actionable signals."""

    def score(self, symbol: str, technicals: TechnicalSignals,
              sentiment: SentimentScore, regime: Regime,
              current_price: float = 0) -> ConfidenceResult:
        """Score a stock across all applicable strategies."""

        if regime == Regime.RED_ALERT:
            return ConfidenceResult(
                symbol=symbol,
                overall_confidence=0.0,
                signal=SignalType.NO_TRADE,
                timestamp=datetime.now(),
            )

        strategy_scores = []
        allowed = REGIME_STRATEGY_MAP.get(regime, [])
        toxic = TOXIC_COMBOS.get(regime, set())

        for strategy in Strategy:
            if strategy in toxic:
                strategy_scores.append(StrategyScore(
                    strategy=strategy, score=0.0,
                    reason=f"TOXIC in {regime.value} regime"
                ))
                continue

            score = self._score_strategy(strategy, technicals, sentiment, regime, current_price)
            strategy_scores.append(score)

        # Find best strategy
        valid_scores = [s for s in strategy_scores if s.strategy in allowed and s.score > 0]
        valid_scores.sort(key=lambda s: s.score, reverse=True)
        best = valid_scores[0] if valid_scores else None

        # Calculate overall confidence
        overall = self._calculate_overall(technicals, sentiment, regime, best)

        # Determine signal
        if overall >= 0.60:
            signal = SignalType.STRONG_BUY
        elif overall >= 0.40:
            signal = SignalType.BUY
        elif overall >= 0.20:
            signal = SignalType.HOLD
        else:
            signal = SignalType.NO_TRADE

        return ConfidenceResult(
            symbol=symbol,
            overall_confidence=overall,
            signal=signal,
            best_strategy=best.strategy if best else None,
            strategy_scores=strategy_scores,
            technical=technicals,
            sentiment=sentiment,
            timestamp=datetime.now(),
        )

    def _score_strategy(self, strategy: Strategy, tech: TechnicalSignals,
                        sent: SentimentScore, regime: Regime,
                        price: float) -> StrategyScore:
        """Score a single strategy for this stock."""
        score = 0.0
        reasons = []

        if strategy == Strategy.ORB_BREAKOUT:
            if tech.confluence_score >= 6:
                score = 0.8
                reasons.append(f"Confluence {tech.confluence_score}/10")
            elif tech.confluence_score >= 5:
                score = 0.6
                reasons.append(f"Confluence {tech.confluence_score}/10")
            if tech.above_vwap:
                score += 0.1
            if tech.macd_histogram > 0:
                score += 0.1

        elif strategy == Strategy.VWAP_BOUNCE:
            if tech.above_vwap and tech.price_vs_vwap < tech.vwap * 0.003:
                score = 0.5
                reasons.append("Near VWAP from above")
            if 35 <= tech.rsi <= 65:
                score += 0.1
                reasons.append("RSI in bounce zone")

        elif strategy == Strategy.GAP_AND_GO:
            # Requires gap detection from data collector
            if tech.above_vwap and tech.macd_histogram > 0:
                score = 0.5
                reasons.append("Above VWAP + MACD positive")

        elif strategy == Strategy.QUICK_FLIP:
            if tech.rsi > 70 or tech.rsi < 30:
                score = 0.6
                reasons.append(f"RSI extreme ({tech.rsi})")
            if tech.macd_histogram < 0 and tech.rsi > 70:
                score += 0.2
                reasons.append("Overbought + MACD divergence")

        elif strategy == Strategy.TOUCH_AND_TURN:
            if tech.orb_low > 0 and price and price <= tech.orb_low * 1.002:
                score = 0.5
                reasons.append("At ORB low (bounce zone)")

        elif strategy == Strategy.FAIR_VALUE_GAP:
            # FVG needs 3-candle gap pattern detection
            if tech.above_vwap and tech.macd > 0:
                score = 0.4
                reasons.append("Trending with positive MACD")

        elif strategy == Strategy.RED_TO_GREEN:
            if tech.rsi < 40 and tech.volume_ratio > 1.2:
                score = 0.6
                reasons.append(f"Oversold RSI {tech.rsi} + volume {tech.volume_ratio}x")

        elif strategy == Strategy.FIVE_MIN_SCALP:
            if tech.volume_ratio > 1.5 and tech.macd_histogram > 0:
                score = 0.5
                reasons.append("High volume + momentum")

        elif strategy == Strategy.BLUE_CHIP_REVERSION:
            if tech.rsi < 30:
                score = 0.8
                reasons.append(f"Extreme oversold RSI {tech.rsi}")
            elif tech.rsi < 40:
                score = 0.5
                reasons.append(f"Oversold RSI {tech.rsi}")
            if sent.total_score >= 3:
                score += 0.1
                reasons.append("Positive sentiment supports bounce")

        elif strategy == Strategy.SMA_TREND_FOLLOW:
            if tech.sma_20 > 0 and price and price > tech.sma_20:
                score = 0.4
                reasons.append("Above 20 SMA")
            if tech.ema_9 > tech.ema_21:
                score += 0.2
                reasons.append("EMA 9 > EMA 21 (uptrend)")

        elif strategy == Strategy.SECTOR_MOMENTUM:
            if sent.total_score >= 5 and tech.volume_ratio > 1.5:
                score = 0.5
                reasons.append("Strong sentiment + high volume")

        # Clamp 0-1
        score = max(0.0, min(1.0, score))
        return StrategyScore(strategy=strategy, score=score, reason="; ".join(reasons))

    def _calculate_overall(self, tech: TechnicalSignals, sent: SentimentScore,
                           regime: Regime, best_strategy: StrategyScore = None) -> float:
        """Calculate weighted overall confidence."""
        components = {}

        # Technical score (RSI position, MACD, VWAP)
        tech_score = 0.5
        if tech.is_oversold:
            tech_score = 0.8  # Strong buy zone
        elif tech.is_overbought:
            tech_score = 0.1  # Danger zone
        if tech.above_vwap:
            tech_score += 0.1
        if tech.macd_histogram > 0:
            tech_score += 0.1
        components['technical'] = min(1.0, tech_score)

        # Sentiment score (normalize -15 to +15 → 0 to 1)
        components['sentiment'] = max(0, min(1, (sent.total_score + 15) / 30))

        # Strategy fit
        components['strategy_fit'] = best_strategy.score if best_strategy else 0

        # Momentum (EMA crossover)
        if tech.ema_9 > 0 and tech.ema_21 > 0:
            components['momentum'] = 0.7 if tech.ema_9 > tech.ema_21 else 0.3
        else:
            components['momentum'] = 0.5

        # Analyst
        components['analyst'] = max(0, min(1, (sent.analyst_score + 5) / 10))

        # Volume
        components['volume'] = min(1.0, tech.volume_ratio / 2)

        # Regime bonus
        if regime == Regime.BULL:
            components['regime_bonus'] = 0.8
        elif regime == Regime.BEAR:
            components['regime_bonus'] = 0.3
        else:
            components['regime_bonus'] = 0.5

        # Weighted sum
        overall = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)
        return round(min(1.0, overall), 3)

    def score_batch(self, symbols: list[str],
                    technicals: dict[str, TechnicalSignals],
                    sentiments: dict[str, SentimentScore],
                    regime: Regime,
                    prices: dict[str, float] = None) -> list[ConfidenceResult]:
        """Score multiple stocks and return sorted by confidence."""
        prices = prices or {}
        results = []
        for sym in symbols:
            tech = technicals.get(sym, TechnicalSignals(symbol=sym))
            sent = sentiments.get(sym, SentimentScore(symbol=sym))
            price = prices.get(sym, 0)
            result = self.score(sym, tech, sent, regime, price)
            results.append(result)

        results.sort(key=lambda r: r.overall_confidence, reverse=True)
        return results
