"""
Beast v2.0 — ARCHITECTURE RULES (READ THIS FIRST)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RULE 1: USE ALL DATA SOURCES. More data = better decisions.

  📺 TradingView Premium (PRIMARY for technicals):
    - ALL indicators (RSI, MACD, VWAP, BB, EMA, SMA)
    - ALL strategy signals (Pine labels: FVG, R2G, Long, Exit)
    - Historical OHLCV bars (backtesting)
    - Confluence scoring from Pine Script
    - Chart screenshots
    
  🔌 Alpaca (PRIMARY for execution + ADDITIONAL data):
    - Order execution (buy/sell/cancel)
    - Positions and P&L
    - Account equity and buying power
    - Market clock (open/closed)
    - Market movers + most active (runner discovery)
    - Real-time snapshots (price confirmation)
    
  📰 Yahoo Finance (sentiment + fundamentals):
    - News headlines and scoring
    - Analyst ratings and upgrades/downgrades
    - Earnings dates and estimates
    - Stock fundamentals (P/E, revenue, etc.)
    - Historical prices (backup)
    
  📱 Reddit WSB + r/stocks (crowd sentiment):
    - Crowd euphoria/fear (contrarian indicator)
    - Ticker mention frequency
    - WSB daily thread sentiment
    
  🏛️ Google News RSS (breaking news):
    - Trump/tariff monitoring
    - Geopolitical events (Iran, oil, war)
    - Breaking market news
    - Fed/monetary policy
    
  🧠 AI Brain — Claude Opus 4.7 (reasoning layer):
    - Deep stock analysis (reads ALL data from all sources)
    - Bull/Bear debates
    - Sector correlation reasoning
    - Earnings play analysis
    - Trade journal grading
    - Morning briefings
    
  ALL sources feed into the Confidence Engine.
  The more data confirming a signal, the higher the confidence.
  No single source is ignored. No single source is sufficient alone.

RULE 2: Iron Laws are HARDCODED PYTHON:
  - Pure if/else deterministic logic.
  - Cannot be overridden by AI, prompt, or any single data source.
  - ALL sources must agree before a trade is approved.
  
RULE 3: NEVER sell at a loss. EVER. Absolute. No override.
"""

# Data flow — ALL sources converge:
#
# TV (indicators + signals) ──┐
# Alpaca (movers + prices) ───┤
# Yahoo (news + analysts) ────┼──→ Confidence Engine → AI Brain → Iron Laws → Execute
# Reddit (crowd sentiment) ───┤
# Google (Trump + breaking) ──┘

