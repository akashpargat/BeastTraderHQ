# BEAST MODE "G" PROTOCOL — v2.2
# This is what happens EVERY TIME the user types "g"
# NO SHORTCUTS. NO LAZINESS. FULL EXECUTION.
# Last Updated: 2026-04-27 (Session 7a05060d)
# RULE: If you skip ANY phase, you are FAILING. The user WILL call you out.

## PHASE 0: PAST WINNERS CHECK (FIRST THING — 15 seconds)
⚠️ THIS PHASE WAS ADDED BECAUSE WE MISSED NOK FOR 35 MINUTES!
1. Get market movers (top 20 gainers) AND most active (top 20 volume)
2. Cross-reference EVERY ticker against our PAST WINNERS LIST:
   NOK, GOOGL, CRM, META, MSFT, NOW, AMD, NVDA, PLTR, TSLA
3. If ANY past winner appears on movers/active → FLAG IMMEDIATELY
4. Check Yahoo Finance news for flagged stocks
5. If catalyst exists → this is TRADE #1, not an afterthought
6. ALSO check: energy (XOM, OXY, CVX, DVN, HAL), space (RKLB), 
   quantum (IONQ), solar (FSLR, ENPH), gold (GDX)
   DO NOT ONLY SCAN TECH/SEMIS!

## PHASE 1: POSITIONS (30 seconds)
1. Get ALL positions with P&L
2. Get ALL open orders
3. Get account balance + buying power
4. Flag any position below 0% confidence for exit warning

## PHASE 2: TV ANALYSIS ON EACH POSITION (60 seconds)
For EACH position, load on TradingView and get:
- RSI (14)
- MACD + histogram
- VWAP (above/below)
- 20 SMA (slope: up/flat/down)
- 200 SMA (support/resistance)
- Bollinger Bands (at upper/lower/middle)
- Distance from 20 SMA (extended or not)

## PHASE 3: SENTIMENT — ALL SOURCES (60 seconds)
### 3A: Yahoo Finance
For EACH position + top runners, check Yahoo Finance news:
- Latest 3-5 headlines
- Score 1-10 (bull/bear)
- Any red flags (lawsuits, downgrades, cancelled contracts)
- Check `yfinance-get_recommendations` for analyst consensus

### 3B: Reddit Sentiment
- Fetch `reddit.com/r/wallstreetbets/hot.json` (daily thread top comments)
- Fetch `reddit.com/r/stocks/hot.json` (daily discussion)
- Search WSB for our ticker names: `/search.json?q=TICKER&sort=new&restrict_sr=on&t=day`
- Gauge crowd euphoria/fear level (contrarian indicator!)
- If WSB says "can't go down" with 80+ upvotes = CAUTION

### 3C: Analyst Ratings (Yahoo Finance)
- `yfinance-get_recommendations` for top plays
- Strong Buy + Buy % vs Hold + Sell %
- Example: GOOGL 90% buy = green light. QCOM 67% hold = CAUTION.

## PHASE 4: FULL MARKET SECTOR SCAN — NOT JUST TECH! (60 seconds)
⚠️ WE KEEP MISSING ENTIRE SECTORS. SCAN ALL OF THESE:

### 4A: Runners + Most Active
1. Get market movers (top 20 gainers)
2. Get most active by volume (top 20)
3. Filter OUT penny stocks (< $5) and warrants (.WS)
4. Get snapshot prices for all qualified runners

### 4B: SECTOR SCAN (check ALL, not just semis!)
- SEMIS: INTC, AMD, NVDA, QCOM, ARM, MRVL, MU, TSM, AVGO, AMAT, KLAC, LRCX, SNDK, MXL
- MAG 7: GOOGL, AMZN, META, MSFT, AAPL, NVDA, TSLA
- ENERGY/OIL: XOM, CVX, OXY, DVN, HAL, NE (check oil price + Iran news!)
- SOFTWARE/AI: CRM, ORCL, PLTR, NOW, SNOW, DDOG
- SPACE/DEFENSE: RKLB, IONQ, LMT, RTX
- SOLAR: FSLR, ENPH, SEDG
- CONSUMER: NKE, SBUX
- PAST WINNERS: NOK, CRM, NOW (always check these!)

### 4C: WHY CHECK? 
Day 5 we missed NOK (+7.7%, $880 left on table) because we only scanned semis.
Day 4 we missed $6,045 in semi gains because we only scanned 5 chips.
EVERY "g" must scan at least 30 stocks across ALL sectors.

## PHASE 5: MULTI-STRATEGY CONFIDENCE ENGINE (60 seconds)
For EACH runner AND each position, score across ALL strategies:

| Strategy | Signal | Weight |
|----------|--------|--------|
| A: ORB Breakout | Is it breaking opening range? | 10% |
| B: VWAP Bounce | Above/below VWAP? | 10% |
| C: Gap & Go | Did it gap? First 5 min? | 5% |
| F: Fair Value Gap | Trending with gaps? | 10% |
| G: Red to Green | Oversold bounce? | 10% |
| H: 5-Min Scalp | Volume + momentum? | 5% |
| I: Mean Reversion | Blue chip at discount? | 10% |
| J: SMA Trend | 20 SMA slope + distance | 15% |
| Sentiment | News score 1-10 | 15% |
| Open Price | Above/below today's open | 10% |

Score > 60% = STRONG BUY (full position)
Score 40-60% = BUY (half position)
Score 20-40% = WEAK (watch only)
Score < 20% = NO TRADE
Score < 0% = EXIT if holding

## PHASE 6: EARNINGS CALENDAR CHECK (30 seconds)
1. What earnings report TONIGHT after close?
2. What earnings report TOMORROW before open?
3. For each: check sentiment, analyst expectations
4. If bullish + stock running up = FLAG FOR PRE-EARNINGS BUY
5. DO NOT MISS ANOTHER INTC!

## PHASE 7: ACTION RECOMMENDATIONS (output)
Present in this format:

```
POSITIONS: [table with P&L, confidence score, action]
RUNNERS: [top 5 with confidence scores]
EARNINGS: [tonight + tomorrow with sentiment]
RECOMMENDED TRADES: [specific entries with strategy name]
WARNINGS: [positions to exit, risks]
```

## PHASE 8: EXECUTE
- If user approves, execute immediately
- Split strategy: half scalp, half runner
- Set limit sells within 60 seconds of every buy
- Match strategy to stock (don't use G on breakouts!)

## RULES:
- Iron Law 12: Research before every trade (even if user says buy)
- Iron Law 21: Cross-reference movers with past winners FIRST
- Iron Law 22: Scan ALL sectors, not just tech
- Use ALL 10 strategies, not just 1
- Distance from 20 SMA > RSI for buy decisions
- 20 SMA flat = NO TRADE
- Earnings tonight = must analyze by 2 PM
- Paper money = experiment aggressively

## COMMON MISTAKES TO AVOID:
1. TUNNEL VISION on Mag 7 — scan 30+ stocks every "g"
2. Forgetting past winners — NOK, CRM, NOW made us money, check them FIRST
3. Ignoring sectors — oil/energy moves when Iran news hits
4. Setting garbage sell targets — minimum 2% above entry
5. Skipping Reddit — WSB euphoria = contrarian warning
6. Not setting limit sells within 60 seconds of buy
7. Overriding another session's orders without checking
8. Chasing RSI > 80 stocks (ARM 87, MRVL 87 = crashed same day)

## INTELLIGENCE SOURCES (use ALL of them on every "g"):
1. Alpaca MCP: positions, orders, snapshots, movers, most active
2. TradingView: RSI, MACD, VWAP, BB, EMA, SMA (5min AND daily)
3. Yahoo Finance: `yfinance-get_yahoo_finance_news` + `yfinance-get_recommendations`
4. Reddit: `web_fetch` on reddit.com/r/wallstreetbets/hot.json and /r/stocks/hot.json
5. Confidence Engine: score across strategies A-K + sentiment + TV + analysts
