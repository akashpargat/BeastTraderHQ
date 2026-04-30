"""
Beast Terminal V4 — Fundamental Analysis Module
================================================
Pulls PE, PEG, revenue growth, earnings growth, analyst targets,
and generates a REASON for every position: why we hold, what's the plan,
when to exit.

This runs in background learning and stores to ai_trends.
The dashboard reads it to show position intelligence.
"""

import logging
import json

log = logging.getLogger('Beast.Fundamentals')


def analyze_fundamentals(symbol: str) -> dict:
    """Pull ALL fundamental data for a stock from yfinance.
    Returns a complete profile with buy/hold/sell reasoning."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        info = t.info or {}
    except Exception as e:
        log.debug(f"Fundamentals {symbol}: {e}")
        return {'symbol': symbol, 'error': str(e)}

    # Extract key metrics
    pe = info.get('trailingPE') or info.get('forwardPE') or 0
    forward_pe = info.get('forwardPE') or 0
    peg = info.get('pegRatio') or 0
    ps = info.get('priceToSalesTrailing12Months') or 0
    pb = info.get('priceToBook') or 0
    rev_growth = info.get('revenueGrowth') or 0  # decimal (0.5 = 50%)
    earn_growth = info.get('earningsGrowth') or 0
    profit_margin = info.get('profitMargins') or 0
    market_cap = info.get('marketCap') or 0
    sector = info.get('sector') or '?'
    industry = info.get('industry') or '?'
    
    # Analyst targets
    target_high = info.get('targetHighPrice') or 0
    target_low = info.get('targetLowPrice') or 0
    target_mean = info.get('targetMeanPrice') or 0
    recommendation = info.get('recommendationKey') or '?'
    num_analysts = info.get('numberOfAnalystOpinions') or 0
    
    # Current price
    price = info.get('currentPrice') or info.get('regularMarketPrice') or 0
    
    # 52-week range
    week52_high = info.get('fiftyTwoWeekHigh') or 0
    week52_low = info.get('fiftyTwoWeekLow') or 0
    from_52high = ((price - week52_high) / week52_high * 100) if week52_high > 0 else 0
    from_52low = ((price - week52_low) / week52_low * 100) if week52_low > 0 else 0
    
    # Dividend
    div_yield = info.get('dividendYield') or 0
    
    # Upside to target
    upside_pct = ((target_mean - price) / price * 100) if price > 0 and target_mean > 0 else 0

    # ── SCORING: Is this fundamentally a buy? ──
    score = 0
    signals = []
    
    # Value: Low PE is good
    if 0 < forward_pe < 10:
        score += 25
        signals.append(f"Cheap PE {forward_pe:.1f}x")
    elif 0 < forward_pe < 20:
        score += 15
        signals.append(f"Fair PE {forward_pe:.1f}x")
    elif forward_pe > 50:
        score -= 10
        signals.append(f"Expensive PE {forward_pe:.0f}x")
    
    # Growth: High revenue growth is gold
    if rev_growth > 0.5:
        score += 25
        signals.append(f"Rev growth +{rev_growth*100:.0f}%")
    elif rev_growth > 0.2:
        score += 15
        signals.append(f"Rev growth +{rev_growth*100:.0f}%")
    elif rev_growth < -0.1:
        score -= 15
        signals.append(f"Rev declining {rev_growth*100:.0f}%")
    
    # PEG: <1 is undervalued
    if 0 < peg < 0.5:
        score += 20
        signals.append(f"PEG {peg:.2f} screaming undervalued")
    elif 0 < peg < 1:
        score += 10
        signals.append(f"PEG {peg:.2f} undervalued")
    
    # Analyst consensus
    if recommendation in ('strong_buy', 'strongBuy'):
        score += 20
        signals.append(f"STRONG BUY ({num_analysts} analysts)")
    elif recommendation in ('buy',):
        score += 10
        signals.append(f"BUY ({num_analysts} analysts)")
    elif recommendation in ('sell', 'strong_sell'):
        score -= 20
        signals.append(f"SELL rating ({num_analysts} analysts)")
    
    # Upside to target
    if upside_pct > 30:
        score += 15
        signals.append(f"Target ${target_mean:.0f} (+{upside_pct:.0f}% upside)")
    elif upside_pct > 10:
        score += 5
        signals.append(f"Target ${target_mean:.0f} (+{upside_pct:.0f}%)")
    elif upside_pct < -10:
        score -= 10
        signals.append(f"Below target (${target_mean:.0f}, {upside_pct:.0f}%)")
    
    # Earnings growth
    if earn_growth > 1.0:
        score += 15
        signals.append(f"Earnings +{earn_growth*100:.0f}%")
    elif earn_growth > 0.2:
        score += 5
        signals.append(f"Earnings +{earn_growth*100:.0f}%")
    
    # Lynch classification
    if 0 < peg < 1 and rev_growth > 0.2:
        lynch_type = "Fast Grower"
    elif div_yield > 0.03 and rev_growth < 0.1:
        lynch_type = "Stalwart"
    elif rev_growth < -0.1 or (pe > 0 and pe < 8):
        lynch_type = "Turnaround"
    elif market_cap > 200e9:
        lynch_type = "Blue Chip"
    else:
        lynch_type = "Growth"

    # Generate verdict
    if score >= 40:
        verdict = "STRONG FUNDAMENTAL BUY"
    elif score >= 20:
        verdict = "FUNDAMENTALLY ATTRACTIVE"
    elif score >= 0:
        verdict = "NEUTRAL FUNDAMENTALS"
    elif score >= -15:
        verdict = "WEAK FUNDAMENTALS"
    else:
        verdict = "FUNDAMENTALLY AVOID"

    return {
        'symbol': symbol,
        'price': price,
        'sector': sector,
        'industry': industry,
        'market_cap_b': round(market_cap / 1e9, 1) if market_cap else 0,
        'pe': round(pe, 1) if pe else 0,
        'forward_pe': round(forward_pe, 1) if forward_pe else 0,
        'peg': round(peg, 2) if peg else 0,
        'revenue_growth_pct': round(rev_growth * 100, 1),
        'earnings_growth_pct': round(earn_growth * 100, 1),
        'profit_margin_pct': round(profit_margin * 100, 1),
        'analyst_rating': recommendation,
        'num_analysts': num_analysts,
        'target_mean': round(target_mean, 2),
        'target_high': round(target_high, 2),
        'upside_pct': round(upside_pct, 1),
        'div_yield_pct': round(div_yield * 100, 2),
        'week52_high': round(week52_high, 2),
        'week52_low': round(week52_low, 2),
        'from_52high_pct': round(from_52high, 1),
        'from_52low_pct': round(from_52low, 1),
        'fundamental_score': score,
        'signals': signals,
        'verdict': verdict,
        'lynch_type': lynch_type,
    }


def generate_position_reasoning(symbol: str, position: dict, fundamentals: dict,
                                 ai_verdict: dict = None, trends: list = None) -> dict:
    """Generate a HUMAN-READABLE reasoning for why we hold this stock.
    This is what the dashboard shows: 'We hold GOOGL because...'"""
    
    pnl = position.get('unrealized_pl', 0)
    pnl_pct = position.get('pct', 0)
    entry = position.get('avg_entry', 0)
    price = position.get('current_price', 0)
    qty = position.get('qty', 0)
    
    reasons = []
    plan = ""
    exit_strategy = ""
    category = "HOLD"  # HOLD, SCALP, SWING, CORE, CUT
    
    # Fundamental reasoning
    f = fundamentals
    if f.get('fundamental_score', 0) >= 40:
        reasons.append(f"Strong fundamentals: {', '.join(f.get('signals',[])[:3])}")
        category = "CORE"
    elif f.get('fundamental_score', 0) >= 20:
        reasons.append(f"Good fundamentals: {', '.join(f.get('signals',[])[:2])}")
    elif f.get('fundamental_score', 0) < 0:
        reasons.append(f"Weak fundamentals: {', '.join(f.get('signals',[])[:2])}")
        if pnl < 0:
            category = "CUT"
    
    # P&L reasoning
    if pnl_pct > 5:
        reasons.append(f"Running +{pnl_pct:.1f}% — ride the momentum")
        category = "SWING"
        plan = "Let it run with trailing stop. Scalp partial on spikes."
        exit_strategy = f"Trail 3%. Target ${price * 1.1:.0f} (+10%). Stop ${price * 0.97:.0f}"
    elif pnl_pct > 2:
        reasons.append(f"Profit +{pnl_pct:.1f}% — approaching scalp target")
        category = "SCALP"
        plan = "Scalp half at +2-3%, trail rest."
        exit_strategy = f"Scalp at ${entry * 1.02:.2f}. Trail rest 3%."
    elif pnl_pct > 0:
        reasons.append(f"Slightly green +{pnl_pct:.1f}%")
        plan = "Hold for scalp target +2%."
        exit_strategy = f"Scalp target: ${entry * 1.02:.2f}"
    elif pnl_pct > -3:
        reasons.append(f"Slightly red {pnl_pct:.1f}% — within normal range")
        plan = "Hold. Wait for recovery."
        exit_strategy = f"Trail if hits +2%. Cut if hits -5% (non blue chip)."
    elif pnl_pct > -5:
        reasons.append(f"Down {pnl_pct:.1f}% — monitor closely")
        plan = "Consider cutting half if no catalyst."
        exit_strategy = f"Cut half below ${entry * 0.95:.2f}. Hold if blue chip."
        category = "WATCH"
    else:
        reasons.append(f"Deep red {pnl_pct:.1f}% — loss position")
        plan = "Blue chip = hold for recovery. Non-blue = cut losses."
        category = "CUT" if f.get('fundamental_score', 0) < 20 else "HOLD"
    
    # AI verdict
    if ai_verdict:
        action = ai_verdict.get('action', 'HOLD')
        conf = ai_verdict.get('confidence', 0)
        reasoning = ai_verdict.get('reasoning', '')
        reasons.append(f"AI says {action} ({conf}%): {reasoning[:60]}")
    
    # Trends
    if trends:
        for t in trends[:2]:
            ttype = t.get('trend_type', '')
            if 'backtest' in ttype:
                reasons.append(f"Backtest: {t.get('insight','')[:60]}")
            elif 'congress' in ttype:
                reasons.append(f"Congress: {t.get('insight','')[:60]}")
            elif 'insider' in ttype:
                reasons.append(f"Insider: {t.get('insight','')[:60]}")
    
    # Analyst target
    if f.get('target_mean', 0) > 0 and f.get('upside_pct', 0) > 5:
        reasons.append(f"Analyst target ${f['target_mean']:.0f} (+{f['upside_pct']:.0f}% upside)")

    return {
        'symbol': symbol,
        'category': category,  # CORE, SWING, SCALP, HOLD, WATCH, CUT
        'reasons': reasons,
        'plan': plan,
        'exit_strategy': exit_strategy,
        'fundamentals': f,
        'summary': f"{category}: {reasons[0] if reasons else 'No clear signal'}"
    }
