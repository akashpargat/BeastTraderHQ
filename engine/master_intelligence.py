"""
Beast v2.0 — MASTER INTELLIGENCE ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE BRAIN. Combines:
  - Akash's 11 strategies (A-K) + Akash Method
  - Reddit WSB/r/algotrading proven patterns
  - Hedge fund quant strategies (momentum, mean reversion, pairs)
  - Institutional flow (dark pool, unusual options activity)
  - Buffett/Wood/Burry/Tom Lee intelligence
  - Sector rotation & correlation engine
  - Multi-timeframe confluence scoring
  - Confidence-based position management system

CONFIDENCE LEVELS (THE CORE DECISION FRAMEWORK):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  90-100%  → CONVICTION BUY: Max size, SWING hold, add on dips
  80-89%   → STRONG BUY: Full size, split scalp+runner
  70-79%   → BUY: Standard size, scalp-heavy (70% scalp / 30% runner)  
  60-69%   → LEAN BUY: Half size, scalp only, tight stops
  50-59%   → WATCH: No trade yet, add to watchlist, wait for better entry
  40-49%   → WEAK: Do nothing, monitor only
  30-39%   → BEARISH: If holding, tighten stops. No new entries.
  20-29%   → STRONG SELL signal: If holding GREEN, take profits NOW
  0-19%    → EXIT: If green, sell immediately. If red, HOLD (Iron Law 1)

POSITION TYPE BY CONFIDENCE:
  90%+ → SWING (hold days/weeks, wide stops, ride the trend)
  70-89% → SPLIT (half scalp for quick profit, half runner for trend)
  60-69% → SCALP ONLY (in and out same day, tight target)
  <60% → NO TRADE
"""
import logging
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger('Beast.Intelligence')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 1: CONFIDENCE ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TradeAction(Enum):
    CONVICTION_BUY = "CONVICTION_BUY"  # 90%+ max size, swing
    STRONG_BUY = "STRONG_BUY"          # 80-89% full size, split
    BUY = "BUY"                        # 70-79% standard, scalp-heavy
    LEAN_BUY = "LEAN_BUY"             # 60-69% half size, scalp only
    WATCH = "WATCH"                    # 50-59% monitor
    HOLD = "HOLD"                      # 40-49% do nothing
    BEARISH = "BEARISH"               # 30-39% tighten stops
    TAKE_PROFIT = "TAKE_PROFIT"       # 20-29% sell if green
    EXIT = "EXIT"                      # 0-19% exit if green


class PositionType(Enum):
    SWING = "SWING"           # Hold days/weeks. 90%+ confidence
    SPLIT = "SPLIT"           # Half scalp + half runner. 70-89%
    SCALP = "SCALP"           # Same-day exit. 60-69%
    NO_TRADE = "NO_TRADE"     # Below 60%


@dataclass
class ConfidenceBreakdown:
    """Complete confidence scoring with every component visible."""
    symbol: str
    
    # Component scores (each 0-100)
    technical_score: float = 0      # RSI, MACD, VWAP, BB, EMA
    sentiment_score: float = 0      # Yahoo + Reddit + analyst
    strategy_fit: float = 0         # How well it matches strategies A-K
    momentum_score: float = 0       # Price action, volume, trend
    institutional_score: float = 0  # Buffett/Wood/Burry alignment
    sector_score: float = 0         # Sector rotation, correlation
    catalyst_score: float = 0       # News, earnings, events
    risk_score: float = 0           # Downside protection signals
    
    # Weighted final
    overall: float = 0              # 0-100 final confidence
    action: TradeAction = TradeAction.HOLD
    position_type: PositionType = PositionType.NO_TRADE
    
    # Position sizing
    size_pct: float = 0             # % of equity to allocate
    scalp_pct: float = 0            # % of position for scalp
    runner_pct: float = 0           # % of position for runner
    
    # Targets
    entry_price: float = 0
    scalp_target: float = 0         # Quick profit target
    runner_target: float = 0        # Extended target
    stop_price: float = 0           # Stop loss
    
    best_strategy: str = ""
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


# Component weights for final score
WEIGHTS = {
    'technical': 0.25,      # TV indicators (RSI, MACD, VWAP, BB)
    'sentiment': 0.12,      # Yahoo + Reddit + news
    'strategy_fit': 0.18,   # Match to strategies A-K
    'momentum': 0.15,       # Price action, volume surge, trend
    'institutional': 0.08,  # Buffett/Wood/Burry overlap
    'sector': 0.07,         # Sector momentum, rotation
    'catalyst': 0.10,       # Earnings, news, events
    'risk': 0.05,           # VIX, correlation, max DD
}


class MasterConfidenceEngine:
    """
    The ultimate scoring engine. Combines EVERYTHING.
    """
    
    def score(self, symbol: str, data: dict) -> ConfidenceBreakdown:
        """Score a stock with full confidence breakdown.
        
        Args:
            data: dict with keys:
                rsi, macd, macd_hist, vwap_above, bb_position,
                ema_9, ema_21, sma_20, sma_200, volume_ratio,
                confluence, yahoo_score, reddit_score, analyst_score,
                regime, price, prev_close, gap_pct, sector,
                earnings_days, buffett_holds, wood_holds, burry_holds
        """
        result = ConfidenceBreakdown(symbol=symbol)
        
        # ── TECHNICAL (25%) ────────────────────────────
        result.technical_score = self._score_technical(data, result)
        
        # ── SENTIMENT (12%) ────────────────────────────
        result.sentiment_score = self._score_sentiment(data, result)
        
        # ── STRATEGY FIT (18%) ─────────────────────────
        result.strategy_fit = self._score_strategy_fit(data, result)
        
        # ── MOMENTUM (15%) ─────────────────────────────
        result.momentum_score = self._score_momentum(data, result)
        
        # ── INSTITUTIONAL (8%) ─────────────────────────
        result.institutional_score = self._score_institutional(data, result)
        
        # ── SECTOR (7%) ────────────────────────────────
        result.sector_score = self._score_sector(data, result)
        
        # ── CATALYST (10%) ─────────────────────────────
        result.catalyst_score = self._score_catalyst(data, result)
        
        # ── RISK (5%) ──────────────────────────────────
        result.risk_score = self._score_risk(data, result)
        
        # ── WEIGHTED FINAL SCORE ───────────────────────
        result.overall = round(
            result.technical_score * WEIGHTS['technical'] +
            result.sentiment_score * WEIGHTS['sentiment'] +
            result.strategy_fit * WEIGHTS['strategy_fit'] +
            result.momentum_score * WEIGHTS['momentum'] +
            result.institutional_score * WEIGHTS['institutional'] +
            result.sector_score * WEIGHTS['sector'] +
            result.catalyst_score * WEIGHTS['catalyst'] +
            result.risk_score * WEIGHTS['risk'],
            1
        )
        
        # ── DETERMINE ACTION + POSITION TYPE ──────────
        self._set_action(result, data)
        
        # ── SET TARGETS ────────────────────────────────
        self._set_targets(result, data)
        
        return result
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # COMPONENT SCORERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _score_technical(self, data: dict, result: ConfidenceBreakdown) -> float:
        """Technical indicators from TradingView Premium."""
        score = 50  # Neutral base
        rsi = data.get('rsi', 50)
        macd_hist = data.get('macd_hist', 0)
        vwap_above = data.get('vwap_above', False)
        volume_ratio = data.get('volume_ratio', 1.0)
        ema_9 = data.get('ema_9', 0)
        ema_21 = data.get('ema_21', 0)
        bb_position = data.get('bb_position', 'mid')  # upper/mid/lower/below
        confluence = data.get('confluence', 0)
        
        # RSI scoring (Akash Method: oversold = buy signal)
        if rsi < 25:
            score += 30; result.reasons.append(f"RSI {rsi} EXTREME oversold 🔥")
        elif rsi < 30:
            score += 25; result.reasons.append(f"RSI {rsi} oversold — bounce zone")
        elif rsi < 40:
            score += 15; result.reasons.append(f"RSI {rsi} approaching oversold")
        elif 40 <= rsi <= 60:
            score += 5;  result.reasons.append(f"RSI {rsi} neutral")
        elif rsi > 80:
            score -= 25; result.warnings.append(f"RSI {rsi} EXTREME overbought ⚠️")
        elif rsi > 70:
            score -= 15; result.warnings.append(f"RSI {rsi} overbought — don't buy")
        
        # MACD momentum
        if macd_hist > 0:
            score += 10; result.reasons.append("MACD histogram positive ✅")
        elif macd_hist < -0.5:
            score -= 10; result.warnings.append("MACD strongly negative")
        
        # VWAP (the most important indicator per skill)
        if vwap_above:
            score += 10; result.reasons.append("Above VWAP ✅")
        else:
            score -= 5; result.warnings.append("Below VWAP ⚠️")
        
        # Volume confirmation (Reddit consensus: volume > 1.2x = real move)
        if volume_ratio > 2.0:
            score += 15; result.reasons.append(f"Volume {volume_ratio}x — massive interest")
        elif volume_ratio > 1.5:
            score += 10; result.reasons.append(f"Volume {volume_ratio}x — strong")
        elif volume_ratio > 1.2:
            score += 5;  result.reasons.append(f"Volume {volume_ratio}x — above avg")
        elif volume_ratio < 0.5:
            score -= 10; result.warnings.append("Low volume — weak conviction")
        
        # EMA alignment (hedge fund trend signal)
        if ema_9 > ema_21 > 0:
            score += 10; result.reasons.append("EMA 9 > 21 — uptrend ✅")
        elif ema_9 < ema_21 > 0:
            score -= 5; result.warnings.append("EMA 9 < 21 — downtrend")
        
        # Bollinger position (mean reversion from hedge fund playbook)
        if bb_position == 'below':
            score += 15; result.reasons.append("Below Bollinger lower — mean reversion buy")
        elif bb_position == 'lower':
            score += 8
        elif bb_position == 'upper':
            score -= 5
        
        # Confluence (from Monster Combo backtested system)
        if confluence >= 8:
            score += 15; result.reasons.append(f"Confluence {confluence}/10 — very strong")
        elif confluence >= 6:
            score += 10; result.reasons.append(f"Confluence {confluence}/10 — good")
        elif confluence >= 5:
            score += 5
        
        return max(0, min(100, score))
    
    def _score_sentiment(self, data: dict, result: ConfidenceBreakdown) -> float:
        """News + Reddit + analyst sentiment."""
        score = 50
        yahoo = data.get('yahoo_score', 0)      # -5 to +5
        reddit = data.get('reddit_score', 0)     # -5 to +5
        analyst = data.get('analyst_score', 0)   # -5 to +5
        
        # Yahoo news impact
        score += yahoo * 5  # Each point = 5% swing
        if yahoo >= 3:
            result.reasons.append(f"Yahoo sentiment very bullish ({yahoo}/5)")
        elif yahoo <= -3:
            result.warnings.append(f"Yahoo sentiment very bearish ({yahoo}/5)")
        
        # Reddit WSB/r/stocks (contrarian check from hedge fund playbook)
        score += reddit * 3
        if reddit >= 4:
            # WSB too euphoric = potential contrarian signal
            result.warnings.append(f"Reddit WSB euphoric ({reddit}/5) — contrarian caution")
            score -= 5  # Slight penalty for extreme FOMO
        elif reddit <= -3:
            result.reasons.append(f"Reddit bearish ({reddit}/5) — potential oversold bounce")
        
        # Analyst consensus (institutional weight)
        score += analyst * 4
        if analyst >= 4:
            result.reasons.append(f"Analysts: Strong Buy ({analyst}/5)")
        
        return max(0, min(100, score))
    
    def _score_strategy_fit(self, data: dict, result: ConfidenceBreakdown) -> float:
        """How well does this stock match our 11 strategies?"""
        score = 0
        regime = data.get('regime', 'CHOPPY')
        rsi = data.get('rsi', 50)
        vwap_above = data.get('vwap_above', False)
        macd_hist = data.get('macd_hist', 0)
        gap_pct = data.get('gap_pct', 0)
        volume_ratio = data.get('volume_ratio', 1.0)
        confluence = data.get('confluence', 0)
        price = data.get('price', 0)
        prev_close = data.get('prev_close', 0)
        
        strategies_matched = []
        
        # Strategy A: ORB Breakout (best BULL + CHOPPY)
        if confluence >= 5 and regime in ('BULL', 'CHOPPY'):
            s = min(30, confluence * 3)
            score += s
            strategies_matched.append(f"A:ORB({confluence})")
        
        # Strategy B: VWAP Bounce
        if vwap_above and rsi < 55 and macd_hist > 0:
            score += 15
            strategies_matched.append("B:VWAP_Bounce")
        
        # Strategy C: Gap & Go
        if gap_pct > 0.01 and vwap_above and volume_ratio > 1.2:
            score += 20
            strategies_matched.append(f"C:Gap&Go({gap_pct:.1%})")
        
        # Strategy F: Fair Value Gap
        if vwap_above and macd_hist > 0 and regime == 'BULL':
            score += 10
            strategies_matched.append("F:FVG")
        
        # Strategy G: Red to Green (THE AKASH METHOD)
        if price > 0 and prev_close > 0 and price > prev_close and rsi < 40:
            score += 25
            strategies_matched.append("G:R2G(AkashMethod)")
            result.reasons.append("🔥 AKASH METHOD: Oversold dip → crossing green")
        
        # Strategy I: Blue Chip Mean Reversion
        if rsi < 30 and data.get('is_blue_chip', False):
            score += 30
            strategies_matched.append("I:MeanReversion")
            result.reasons.append("💎 Blue chip at extreme oversold — Mean Reversion")
        
        # Strategy J: SMA Trend Follow
        sma_20 = data.get('sma_20', 0)
        if price > sma_20 > 0 and data.get('ema_9', 0) > data.get('ema_21', 0):
            score += 15
            strategies_matched.append("J:SMA_Trend")
        
        if strategies_matched:
            result.best_strategy = strategies_matched[0]
            result.reasons.append(f"Strategies: {', '.join(strategies_matched)}")
        
        return max(0, min(100, score))
    
    def _score_momentum(self, data: dict, result: ConfidenceBreakdown) -> float:
        """Price action momentum — Reddit proven: volume + trend = edge."""
        score = 50
        volume_ratio = data.get('volume_ratio', 1.0)
        price = data.get('price', 0)
        prev_close = data.get('prev_close', 0)
        
        # Intraday momentum
        if price > 0 and prev_close > 0:
            day_change = (price - prev_close) / prev_close
            if day_change > 0.03:
                score += 20; result.reasons.append(f"Running +{day_change:.1%} today 🏃")
            elif day_change > 0.01:
                score += 10
            elif day_change < -0.03:
                # Oversold bounce candidate (Akash Method)
                if data.get('rsi', 50) < 35:
                    score += 15; result.reasons.append("Deep dip + oversold = bounce play")
                else:
                    score -= 10
        
        # Volume confirms the move
        if volume_ratio > 2.0:
            score += 15
        elif volume_ratio > 1.5:
            score += 8
        
        return max(0, min(100, score))
    
    def _score_institutional(self, data: dict, result: ConfidenceBreakdown) -> float:
        """Institutional alignment — follow the smart money."""
        score = 50
        symbol = data.get('symbol', '')
        
        # Buffett holdings (value, safety)
        BUFFETT = {'AAPL', 'AXP', 'BAC', 'KO', 'CVX', 'OXY', 'CB'}
        if symbol in BUFFETT:
            score += 15; result.reasons.append("Buffett holds this 🏛️")
        
        # Cathie Wood / ARK (innovation, growth)
        WOOD = {'TSLA', 'SHOP', 'ROKU', 'COIN', 'PLTR', 'AMD', 'HOOD', 'CRSP'}
        if symbol in WOOD:
            score += 10; result.reasons.append("Cathie Wood/ARK holds this 🚀")
        
        # Burry (contrarian bets)
        BURRY = {'BABA', 'LULU', 'MOH'}
        if symbol in BURRY:
            score += 5; result.reasons.append("Burry contrarian position")
        
        # Overlap check (multiple institutions = strong)
        institutions_holding = sum([
            symbol in BUFFETT, symbol in WOOD, symbol in BURRY
        ])
        if institutions_holding >= 2:
            score += 10; result.reasons.append("Multiple institutional holders ✅")
        
        # Goldman Sachs S&P 7600 target (bull bias for large cap)
        if data.get('is_sp500', False):
            score += 5
        
        return max(0, min(100, score))
    
    def _score_sector(self, data: dict, result: ConfidenceBreakdown) -> float:
        """Sector rotation and correlation analysis."""
        score = 50
        sector = data.get('sector', '')
        sector_momentum = data.get('sector_momentum', 0)  # -1 to +1
        
        if sector_momentum > 0.5:
            score += 20; result.reasons.append(f"Sector {sector} strong momentum 🔥")
        elif sector_momentum > 0.2:
            score += 10
        elif sector_momentum < -0.3:
            score -= 15; result.warnings.append(f"Sector {sector} weak — dragging down")
        
        return max(0, min(100, score))
    
    def _score_catalyst(self, data: dict, result: ConfidenceBreakdown) -> float:
        """News catalysts, earnings plays, events."""
        score = 50
        earnings_days = data.get('earnings_days', 999)
        has_news_catalyst = data.get('has_catalyst', False)
        
        # Earnings proximity (from Day 3 lesson: INTC miss cost us $500)
        if earnings_days == 0:
            score -= 30; result.warnings.append("⛔ EARNINGS TODAY — no new trades")
        elif earnings_days == 1:
            score -= 20; result.warnings.append("⚠️ Earnings tomorrow — caution")
        elif 2 <= earnings_days <= 3:
            # Pre-earnings run-up (Day 3 INTC lesson: stock running = institutions know)
            if data.get('price_vs_prev', 0) > 0.02:
                score += 20
                result.reasons.append("📈 Running into earnings — smart money positioning")
        
        # News catalyst
        if has_news_catalyst:
            score += 15; result.reasons.append("News catalyst present ✅")
        
        return max(0, min(100, score))
    
    def _score_risk(self, data: dict, result: ConfidenceBreakdown) -> float:
        """Downside risk assessment."""
        score = 70  # Start optimistic (paper trading = experiment)
        
        vix = data.get('vix', 20)
        if vix > 30:
            score -= 20; result.warnings.append(f"VIX {vix} — high fear")
        elif vix > 25:
            score -= 10
        elif vix < 15:
            score += 10; result.reasons.append(f"VIX {vix} — calm market")
        
        # Max drawdown history for this stock
        max_dd = data.get('max_drawdown', 0)
        if max_dd > 0.25:
            score -= 15; result.warnings.append(f"High max drawdown {max_dd:.0%}")
        
        return max(0, min(100, score))
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ACTION & POSITION SIZING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _set_action(self, result: ConfidenceBreakdown, data: dict):
        """Set trade action, position type, and sizing based on confidence."""
        c = result.overall
        
        if c >= 90:
            result.action = TradeAction.CONVICTION_BUY
            result.position_type = PositionType.SWING
            result.size_pct = 0.10          # 10% of equity
            result.scalp_pct = 0.30         # 30% scalp
            result.runner_pct = 0.70        # 70% runner (swing)
            result.reasons.append("🔥 CONVICTION BUY — max size, SWING hold")
        
        elif c >= 80:
            result.action = TradeAction.STRONG_BUY
            result.position_type = PositionType.SPLIT
            result.size_pct = 0.08          # 8% of equity
            result.scalp_pct = 0.50         # 50/50 split
            result.runner_pct = 0.50
            result.reasons.append("💪 STRONG BUY — full size, split position")
        
        elif c >= 70:
            result.action = TradeAction.BUY
            result.position_type = PositionType.SPLIT
            result.size_pct = 0.06          # 6%
            result.scalp_pct = 0.70         # 70% scalp, 30% runner
            result.runner_pct = 0.30
            result.reasons.append("🟢 BUY — standard size, scalp-heavy")
        
        elif c >= 60:
            result.action = TradeAction.LEAN_BUY
            result.position_type = PositionType.SCALP
            result.size_pct = 0.04          # 4% — smaller
            result.scalp_pct = 1.0          # 100% scalp, no runner
            result.runner_pct = 0.0
            result.reasons.append("📊 LEAN BUY — half size, scalp only")
        
        elif c >= 50:
            result.action = TradeAction.WATCH
            result.position_type = PositionType.NO_TRADE
            result.size_pct = 0
        
        elif c >= 40:
            result.action = TradeAction.HOLD
            result.position_type = PositionType.NO_TRADE
            result.size_pct = 0
        
        elif c >= 30:
            result.action = TradeAction.BEARISH
            result.position_type = PositionType.NO_TRADE
            result.size_pct = 0
            result.warnings.append("⚠️ BEARISH — tighten stops on holdings")
        
        elif c >= 20:
            result.action = TradeAction.TAKE_PROFIT
            result.position_type = PositionType.NO_TRADE
            result.size_pct = 0
            result.warnings.append("💰 TAKE PROFIT — sell if green")
        
        else:
            result.action = TradeAction.EXIT
            result.position_type = PositionType.NO_TRADE
            result.size_pct = 0
            result.warnings.append("🚪 EXIT signal — sell if green, HOLD if red (Law 1)")
        
        # Sentiment multiplier (from skill file)
        sentiment_total = (data.get('yahoo_score', 0) + 
                          data.get('reddit_score', 0) + 
                          data.get('analyst_score', 0))
        if sentiment_total >= 8:
            result.size_pct *= 1.5  # Aggressive
        elif sentiment_total <= -5:
            result.size_pct *= 0.5  # Defensive
        elif sentiment_total <= -8:
            result.size_pct = 0     # Abort
            result.action = TradeAction.HOLD
            result.warnings.append("⛔ Sentiment ABORT — no trades")
    
    def _set_targets(self, result: ConfidenceBreakdown, data: dict):
        """Set entry, scalp target, runner target, and stop based on confidence."""
        price = data.get('price', 0)
        if price <= 0:
            return
        
        result.entry_price = round(price, 2)
        
        # Targets scale with confidence
        c = result.overall
        
        # SESSION RULE: Minimum +2% scalp, +5% runner. NEVER less.
        # "NEVER set a sell at +0.03% like $263.75 on a $262.63 buy. 
        #  That's GIVING AWAY MONEY." — Senior Trader Session 7a05060d
        
        if c >= 90:
            # SWING: wide targets, hold for big move
            result.scalp_target = round(price * 1.03, 2)   # 3% scalp
            result.runner_target = round(price * 1.08, 2)   # 8% runner
            result.stop_price = round(price * 0.95, 2)      # 5% stop (wide for swing)
        elif c >= 80:
            result.scalp_target = round(price * 1.025, 2)   # 2.5% scalp
            result.runner_target = round(price * 1.06, 2)    # 6% runner
            result.stop_price = round(price * 0.97, 2)       # 3% stop
        elif c >= 70:
            result.scalp_target = round(price * 1.02, 2)    # 2% scalp (MINIMUM)
            result.runner_target = round(price * 1.05, 2)    # 5% runner (MINIMUM)
            result.stop_price = round(price * 0.98, 2)       # 2% stop
        elif c >= 60:
            result.scalp_target = round(price * 1.02, 2)    # 2% (minimum, scalp only)
            result.runner_target = 0                         # No runner at this confidence
            result.stop_price = round(price * 0.985, 2)      # 1.5% stop
        
        # Akash Method override: If RSI < 30, use wider targets (bounce = bigger)
        rsi = data.get('rsi', 50)
        if rsi < 30 and c >= 60:
            # Akash Method BUT must respect 2% minimum from SESSION_RULES
            akash_scalp = round(price * 1.025, 2)   # 2.5% bounce minimum
            akash_runner = round(price * 1.06, 2)    # 6% recovery
            result.scalp_target = max(result.scalp_target, akash_scalp)
            result.runner_target = max(result.runner_target, akash_runner)
            result.reasons.append(f"🎯 Akash Method: oversold RSI {rsi} → scalp +2.5%, runner +6%")
        
        # ENFORCE SESSION RULES: minimum 2% scalp, 5% runner
        min_scalp = round(price * 1.02, 2)
        min_runner = round(price * 1.05, 2)
        if result.scalp_target > 0 and result.scalp_target < min_scalp:
            result.scalp_target = min_scalp
            result.warnings.append(f"📏 Scalp raised to +2% minimum (${min_scalp})")
        if result.runner_target > 0 and result.runner_target < min_runner:
            result.runner_target = min_runner
            result.warnings.append(f"📏 Runner raised to +5% minimum (${min_runner})")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 2: PREMARKET INTELLIGENCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Pre-market runner criteria (from Reddit r/Daytrading consensus)
PREMARKET_RUNNER_CRITERIA = {
    'min_gap_pct': 0.02,        # 2% gap minimum
    'min_volume': 50000,        # 50K shares pre-market
    'min_price': 5.0,           # No penny stocks
    'max_price': 500.0,         # Manageable position sizes
    'need_catalyst': True,      # Gap without news = fade
}

# Extended hours order settings
EXTENDED_HOURS_CONFIG = {
    'order_type': 'limit',      # ALWAYS limit in extended hours
    'time_in_force': 'day',     # Day orders for extended
    'extended_hours': True,     # Alpaca flag
    'max_position_pct': 0.03,   # Smaller in pre/post (3% vs 5-10%)
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 3: HEDGE FUND STRATEGY LIBRARY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HEDGE_FUND_STRATEGIES = {
    'momentum_cross': {
        'name': 'Momentum EMA Cross',
        'source': 'Quant hedge funds, proven in academic research',
        'signal': 'EMA 9 crosses above EMA 21',
        'confirmation': 'Volume > 1.5x average',
        'exit': 'EMA 9 crosses below EMA 21',
        'win_rate': '55-60% with trend filter',
        'best_in': ['BULL'],
    },
    'mean_reversion_bb': {
        'name': 'Bollinger Mean Reversion',
        'source': 'John Bollinger, institutional trading desks',
        'signal': 'Price touches lower BB + RSI < 30',
        'confirmation': 'Volume spike + bullish candle',
        'exit': 'Price returns to BB mid',
        'win_rate': '60-65% in range-bound markets',
        'best_in': ['CHOPPY', 'BULL'],
    },
    'z_score_reversion': {
        'name': 'Z-Score Mean Reversion',
        'source': 'Quant funds, stat arb desks',
        'signal': 'Price z-score < -2 vs 20-day MA',
        'confirmation': 'Not in downtrend (SMA 50 > SMA 200)',
        'exit': 'Z-score returns to 0',
        'win_rate': '58% on large caps',
        'best_in': ['CHOPPY'],
    },
    'sector_rotation': {
        'name': 'Sector Rotation Momentum',
        'source': 'Tom Lee/Fundstrat, macro hedge funds',
        'signal': '2+ stocks in sector up >2%, scan all peers',
        'confirmation': 'ETF of sector also up >1%',
        'exit': 'Sector ETF reverses',
        'win_rate': 'High correlation with market regime',
        'best_in': ['BULL', 'BEAR'],
    },
    'dark_pool_follow': {
        'name': 'Dark Pool Level Trading',
        'source': 'Unusual Whales, FlowAlgo, institutional flow',
        'signal': 'Large dark pool prints at a specific level',
        'confirmation': 'Price holds above dark pool level',
        'exit': 'Price breaks below dark pool level',
        'win_rate': '~55% (levels act as support/resistance)',
        'best_in': ['BULL', 'CHOPPY'],
    },
    'unusual_options': {
        'name': 'Unusual Options Activity Follow',
        'source': 'Sweep orders, institutional positioning',
        'signal': 'Options volume 3x+ normal, sweep orders',
        'confirmation': 'Stock price moving in same direction',
        'exit': 'Options expiration or target hit',
        'win_rate': '50-55% but high reward when right',
        'best_in': ['BULL'],
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 4: STOCK CLASSIFICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STOCK_PROFILES = {
    # Blue chips (Strategy I territory)
    'AAPL': {'type': 'blue_chip', 'sectors': ['mag7'], 'volatility': 'low', 'daily_move': 0.015},
    'MSFT': {'type': 'blue_chip', 'sectors': ['mag7', 'cloud'], 'volatility': 'low', 'daily_move': 0.018},
    'GOOGL': {'type': 'blue_chip', 'sectors': ['mag7', 'ai'], 'volatility': 'medium', 'daily_move': 0.02},
    'AMZN': {'type': 'blue_chip', 'sectors': ['mag7', 'retail', 'cloud'], 'volatility': 'medium', 'daily_move': 0.02},
    
    # Offense roster
    'COIN': {'type': 'offense', 'sectors': ['crypto'], 'volatility': 'very_high', 'daily_move': 0.04},
    'TSLA': {'type': 'offense', 'sectors': ['mag7'], 'volatility': 'high', 'daily_move': 0.03},
    'META': {'type': 'offense', 'sectors': ['mag7', 'ai'], 'volatility': 'medium', 'daily_move': 0.015},
    'MSTR': {'type': 'offense', 'sectors': ['crypto'], 'volatility': 'very_high', 'daily_move': 0.05},
    
    # Defense roster
    'CAT': {'type': 'defense', 'sectors': ['defense'], 'volatility': 'medium', 'daily_move': 0.02},
    'ORCL': {'type': 'defense', 'sectors': ['cloud'], 'volatility': 'medium', 'daily_move': 0.028},
    'XOM': {'type': 'defense', 'sectors': ['energy'], 'volatility': 'low', 'daily_move': 0.015},
    'COST': {'type': 'defense', 'sectors': ['retail'], 'volatility': 'low', 'daily_move': 0.01},
    
    # Chips (sector scan)
    'NVDA': {'type': 'chips_leader', 'sectors': ['chips', 'ai', 'mag7'], 'volatility': 'high', 'daily_move': 0.03},
    'AMD': {'type': 'chips', 'sectors': ['chips', 'ai'], 'volatility': 'high', 'daily_move': 0.03},
    'INTC': {'type': 'chips', 'sectors': ['chips'], 'volatility': 'high', 'daily_move': 0.03},
    'TSM': {'type': 'chips', 'sectors': ['chips'], 'volatility': 'medium', 'daily_move': 0.02},
    'AVGO': {'type': 'chips', 'sectors': ['chips', 'ai'], 'volatility': 'medium', 'daily_move': 0.025},
    'QCOM': {'type': 'chips', 'sectors': ['chips'], 'volatility': 'medium', 'daily_move': 0.02},
    'MU': {'type': 'chips', 'sectors': ['chips'], 'volatility': 'high', 'daily_move': 0.03},
    'MRVL': {'type': 'chips', 'sectors': ['chips', 'ai'], 'volatility': 'high', 'daily_move': 0.035},
    'ARM': {'type': 'chips', 'sectors': ['chips', 'ai'], 'volatility': 'very_high', 'daily_move': 0.04},
    
    # Meme / high retail
    'NOK': {'type': 'meme_value', 'sectors': ['meme'], 'volatility': 'medium', 'daily_move': 0.02},
    'PLTR': {'type': 'ai_momentum', 'sectors': ['ai', 'meme'], 'volatility': 'high', 'daily_move': 0.03},
    'HOOD': {'type': 'fintech', 'sectors': ['crypto', 'meme'], 'volatility': 'high', 'daily_move': 0.035},
    'SOFI': {'type': 'fintech', 'sectors': ['meme'], 'volatility': 'high', 'daily_move': 0.03},
    
    # Energy
    'OXY': {'type': 'energy', 'sectors': ['energy'], 'volatility': 'medium', 'daily_move': 0.02},
    'CVX': {'type': 'energy', 'sectors': ['energy'], 'volatility': 'low', 'daily_move': 0.015},
    
    # AI / Cloud
    'CRM': {'type': 'cloud', 'sectors': ['cloud', 'ai'], 'volatility': 'medium', 'daily_move': 0.025},
    'NOW': {'type': 'cloud', 'sectors': ['cloud', 'ai'], 'volatility': 'medium', 'daily_move': 0.025},
    'CRWD': {'type': 'cyber', 'sectors': ['cloud', 'ai'], 'volatility': 'high', 'daily_move': 0.03},
}

def get_stock_profile(symbol: str) -> dict:
    """Get stock profile with defaults for unknown stocks."""
    return STOCK_PROFILES.get(symbol, {
        'type': 'unknown', 'sectors': [], 'volatility': 'medium', 'daily_move': 0.02
    })

def is_blue_chip(symbol: str) -> bool:
    p = get_stock_profile(symbol)
    return p.get('type') in ('blue_chip', 'defense')

def is_chip_stock(symbol: str) -> bool:
    p = get_stock_profile(symbol)
    return 'chips' in p.get('sectors', [])

def get_all_chip_stocks() -> list[str]:
    return [s for s, p in STOCK_PROFILES.items() if 'chips' in p.get('sectors', [])]

def get_stocks_by_sector(sector: str) -> list[str]:
    return [s for s, p in STOCK_PROFILES.items() if sector in p.get('sectors', [])]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 5: AKASH METHOD (PROVEN PROFITABLE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AKASH_METHOD = {
    'name': 'Akash Method — Buy Dip → Limit Sell → Auto-Fill → Repeat',
    'proven_trades': [
        'NOK: Bought $10.16 (RSI 37) → Limit sell $10.30 → +$420',
        'NOW: Bought $84.43 (RSI 11) → Sold $85.20 → +$77',
        'MSFT: Bought $411.63 (RSI 22) → Sold $416.50 → +$122',
    ],
    'rules': {
        'entry': 'RSI < 35 on a stock with no bad news (sector panic OK)',
        'exit': 'Set limit sell IMMEDIATELY at +0.5% to +1.5%',
        'size': '3000 shares of $10 stock > 15 shares of $300 stock',
        'key': 'The limit sell auto-fills. You don\'t watch. You wait.',
        'repeat': 'When filled, look for next oversold dip. Reload.',
    },
    'best_for': ['NOK', 'SOFI', 'PLTR', 'AMD', 'HOOD'],  # Liquid, $5-50 range
    'avoid': ['Low volume stocks', 'Stocks with bad earnings', 'Stocks in free-fall'],
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 6: REDDIT-PROVEN RULES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REDDIT_RULES = [
    # From r/Daytrading top all-time posts
    "Risk 1-2% max per trade. Position size calculator mandatory.",
    "Simulate 6+ months before going live with real money.",
    "Journal EVERY trade including psychology and mistakes.",
    "2 consecutive losses = STOP. Walk away. No revenge trading.",
    "Volume confirms everything. No volume = fake move.",
    "The first 15 minutes are for watching, not trading (except Gap&Go).",
    "Scalping works best in liquid stocks (AAPL, NVDA, TSLA, SPY).",
    "Never chase a stock already up 5%+ (FOMO = 0% win rate).",
    
    # From r/algotrading proven backtests
    "Moving average crossovers work but ONLY with volume confirmation.",
    "RSI + Bollinger Bands = highest win rate combo in 20-year backtest.",
    "Donchian Channel breakouts still work in 2026 on volatile stocks.",
    "Sentiment bots need constant retraining — stale prompts lose money.",
    "Multiple signal blend > single indicator (trend + momentum + reversion).",
    "Backtest illusion is real — account for slippage and order flow.",
    
    # From r/wallstreetbets patterns
    "When WSB is too bullish on something, it's often near the top.",
    "When WSB gives up on a stock entirely, that's often the bottom.",
    "Earnings plays: if stock runs INTO earnings, institutions already know.",
    "Sector moves: when one chip stock moves, check ALL chip stocks.",
    "Oil up = energy stocks up, tech stocks down. Trade the correlation.",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 7: SESSION RULES (from Senior Trader 7a05060d)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SESSION_RULES = {
    'min_scalp_profit_pct': 0.02,   # 2% MINIMUM scalp target
    'min_runner_profit_pct': 0.05,  # 5% MINIMUM runner target
    'split_mandatory': True,        # Every buy = half scalp + half runner
    'past_winners_first': True,     # Phase 0 before everything else
    'scan_all_sectors': True,       # Not just tech — energy, defense, solar, gold
    'tv_before_trade': True,        # TradingView analysis MANDATORY before buy
    'sentiment_before_trade': True, # Yahoo + Reddit MANDATORY before buy
    'check_existing_orders': True,  # Multi-session coordination
}

# Past winners list (from Day 1-5 proven profits)
PAST_WINNERS = [
    'NOK',    # Akash Method king (+$420 Day 3)
    'CRM',    # Sector panic plays (+$120 Day 3)
    'NOW',    # Extreme RSI bounces (+$282 Day 3)
    'GOOGL',  # Blue chip mean reversion (+$396 peak)
    'META',   # Consistent 75% WR in backtests
    'MSFT',   # RSI 22 bounce (+$122 Day 3)
    'AMD',    # Semiconductor momentum (+$131 Day 3)
    'NVDA',   # AI leader, high volume runner
    'PLTR',   # AI software momentum
    'TSLA',   # Clean breakouts, 83% WR
    'ORCL',   # FVG strategy (+$108 backtest)
    'INTC',   # The one we missed — never again (+$500 potential)
]

# Full sector scan list (MANDATORY every "g" cycle)
FULL_SECTOR_SCAN = {
    'semis': ['NVDA', 'AMD', 'INTC', 'TSM', 'AVGO', 'QCOM', 'ARM',
              'MRVL', 'MU', 'AMAT', 'KLAC', 'LRCX', 'MXL'],
    'mag7': ['AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA', 'TSLA'],
    'energy': ['XOM', 'CVX', 'OXY', 'DVN', 'HAL'],
    'software_ai': ['CRM', 'ORCL', 'PLTR', 'NOW', 'SNOW', 'DDOG'],
    'space_defense': ['RKLB', 'IONQ', 'LMT', 'RTX'],
    'solar': ['FSLR', 'ENPH', 'SEDG'],
    'consumer': ['NKE', 'SBUX', 'COST'],
    'crypto': ['COIN', 'MSTR', 'HOOD', 'MARA', 'RIOT'],
    'past_winners': ['NOK', 'CRM', 'NOW'],
    'gold': ['GDX', 'SLV'],
}

def get_all_scan_symbols() -> list[str]:
    """Get every symbol we should scan on a 'g' cycle. 60+ stocks."""
    all_syms = set()
    for sector_stocks in FULL_SECTOR_SCAN.values():
        all_syms.update(sector_stocks)
    all_syms.update(PAST_WINNERS)
    return sorted(all_syms)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 8: BEAST MODE "G" EXECUTION ORDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BEAST_MODE_PHASES = """
🦍 BEAST MODE v2.2 — EXECUTION ORDER (EVERY CYCLE):

PHASE 0: PAST WINNERS CHECK (15 sec)
  → alpaca-get_market_movers + get_most_active_stocks
  → Cross-reference with PAST_WINNERS list
  → If match + catalyst → this is TRADE #1

PHASE 1: POSITIONS (30 sec)
  → alpaca-get_all_positions (P&L on everything)
  → alpaca-get_orders status=open (multi-session check!)
  → alpaca-get_account_info (equity, buying power)

PHASE 2: TRADINGVIEW ON EVERY POSITION (60 sec)
  → For EACH held stock + top runners:
    → tradingview-chart_set_symbol
    → tradingview-data_get_study_values (RSI, MACD, VWAP, BB, EMA)
    → tradingview-data_get_pine_labels (FVG, R2G, Long signals)
    → tradingview-data_get_pine_tables (strategy data)
    → tradingview-quote_get (live price)
  ⛔ NO TRADE WITHOUT TV DATA. PERIOD.

PHASE 3: SENTIMENT — ALL 3 SOURCES (60 sec)
  → 3A: yfinance-get_yahoo_finance_news (each stock)
  → 3B: Reddit WSB + r/stocks (web_fetch hot.json)
  → 3C: yfinance-get_recommendations (analyst consensus)
  ⛔ NO TRADE WITHOUT SENTIMENT. PERIOD.

PHASE 4: FULL SECTOR SCAN — ALL 10 SECTORS (60 sec)
  → Semis, Mag7, Energy, AI/Software, Space/Defense,
    Solar, Consumer, Crypto, Past Winners, Gold
  → 60+ stocks scanned per cycle
  → Flag any sector with 2+ stocks moving >2%

PHASE 5: CONFIDENCE ENGINE (60 sec)
  → Score EVERY stock across:
    Technical (25%) + Sentiment (12%) + Strategy Fit (18%) +
    Momentum (15%) + Institutional (8%) + Sector (7%) +
    Catalyst (10%) + Risk (5%)
  → Confidence → Action:
    90%+ = CONVICTION BUY (swing, max size)
    80%  = STRONG BUY (split scalp+runner)
    70%  = BUY (scalp-heavy)
    60%  = LEAN BUY (scalp only, half size)
    <60% = NO TRADE
  → Targets:
    Scalp: MINIMUM +2% above entry
    Runner: MINIMUM +5% above entry

PHASE 6: EARNINGS CALENDAR (30 sec)
  → What reports tonight? Tomorrow?
  → If stock running into earnings = institutional positioning
  → NEVER MISS ANOTHER INTC

PHASE 7: ACTION TABLE
  → Clear BUY/SELL/HOLD for every stock
  → Specific limit prices (scalp + runner targets)
  → New entry opportunities ranked by confidence

PHASE 8: EXECUTE + RISK CHECK
  → Iron Laws gate everything (hardcoded Python)
  → Split every buy: half scalp + half runner
  → Limit sells set within 60 seconds
  → NEVER SELL AT A LOSS. EVER.
  → Notify via Telegram on every trade
"""
