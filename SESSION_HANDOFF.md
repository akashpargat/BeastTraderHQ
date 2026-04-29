# 🦍 Beast Engine V3 — Complete Handoff for Next Session
# Read this FIRST before doing anything.

## WHAT IS THIS PROJECT
Autonomous AI day trading bot on Azure VM. Paper trading $102K on Alpaca.
13 positions, 18 open orders, dual AI (GPT-4o + Claude), TradingView Premium integration.

## WHERE IS THE CODE
- **GitHub**: https://github.com/akashpargat/BeastTraderHQ (private, personal account)
- **VM**: `C:\beast-test2\` on Azure VM 172.179.234.42 (user: beastadmin / [see .env on VM])
- **Local push repo**: `C:\Users\akashpargat\AppData\Local\Temp\beast_push2` (use this for edits → push)
- **OneDrive copy**: `C:\Users\akashpargat\OneDrive - Microsoft\Desktop\AI-Trading\beast-v3` (may be stale)

## HOW TO EDIT AND PUSH CODE
```cmd
cd C:\Users\akashpargat\AppData\Local\Temp\beast_push2
# edit files here
git add <files>
git commit -m "message

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git -c credential.helper="" push origin master:main --force
```
Then on VM: `git pull` to update.

## HOW TO START ON VM
```cmd
cd C:\beast-test2
git pull
# First time after code changes:
cd dashboard && npm install && npx next build && cd ..
# Then:
START_ALL.bat
```
START_ALL.bat launches: TV Desktop (CDP 9222) → Dashboard API (8080) → Dashboard UI (3000) → Discord Bot

## ARCHITECTURE (key files)
| File | Purpose | Size |
|------|---------|------|
| discord_bot.py | THE main process. Autonomous loops (60s/5min/10min), auto-trading | ~105KB |
| beast_mode_loop.py | Standalone loop with ATR sizing, earnings reaction, shorts | ~117KB |
| ai_brain.py | Hybrid AI: GPT-4o (5min) + Claude Opus 4.7 (30min) | ~18KB |
| order_gateway.py | Single-writer to Alpaca. Trailing stops, quick_buy, anti-buyback | ~23KB |
| sentiment_analyst.py | 9 FREE sources (Yahoo/Reddit/StockTwits/Earnings/Short/Finviz/VIX) | ~24KB |
| tv_analyst.py | Parses TradingView study values into signals | ~10KB |
| tv_cdp_client.py | CDP WebSocket connection to TV Desktop | ~8KB |
| iron_laws.py | 13 hardcoded safety rules + earnings override | ~21KB |
| dashboard_api.py | Flask API (13 endpoints) on port 8080 | ~8KB |
| dashboard/ | Next.js 14 app on port 3000 | dir |
| ARCHITECTURE.md | Complete 30KB+ system documentation | 30KB |

## CREDENTIALS (ALL IN .env ON VM)
- **Alpaca**: PA37M4LP1YKP (key: [see .env], secret in .env)
- **Azure OpenAI**: beast-ai-brain, East US, deployment: gpt4o
  - Endpoint: https://eastus.api.cognitive.microsoft.com/
  - Key: [see .env on VM]
- **Claude tunnel**: ai.beast-trader.com → work laptop localhost:5555 (laptop must be ON)
- **AI API Key**: [see .env on VM]
- **Discord**: Beast Trader#5020, channel: 1498363431013716079
- **Telegram**: @KashKingTraderBot ([see .env], chat: 8795390430)
- **GitHub PAT**: [see .env on VM]
- **Azure sub**: 718ce05c-64d1-48b0-a57e-45dc198ccc69
- **Cloudflare**: beast-trader.com domain, 3 tunnels (ai/dashboard/api)

## CRITICAL LESSONS (DON'T REPEAT THESE MISTAKES)
1. **az vm run-command runs as SYSTEM** — can't see user PATH/env. Use full paths.
2. **TV Desktop needs `--remote-debugging-port=9222`** flag to enable CDP
3. **TV Desktop on VM Server 2022** needs `takeown` on WindowsApps folder first
4. **TV study values are STALE after symbol switch** — wait 5s+ and retry if < 3 studies
5. **Chrome suspends background tabs** → study values empty. TV Desktop doesn't.
6. **Python emoji crashes on Windows cp1252** — always set `PYTHONIOENCODING=utf-8`
7. **All blocking calls in discord_bot MUST use `asyncio.to_thread()`** or Discord heartbeat dies
8. **Check `qty_available` before selling** — shares held by existing orders = unavailable
9. **gateway.place_buy() requires TradeProposal** — use `gateway.quick_buy()` for simple buys
10. **Don't buy back stock at higher price than you sold** — anti-buyback check in quick_buy()

## IRON LAWS (NEVER CHANGE THESE)
1. Never sell at loss (EXCEPTION: non-blue-chip earnings miss >10% drop)
2. Limit orders ONLY
3-13. See iron_laws.py

Blue chips that ALWAYS hold: AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA, JPM, V, MA, etc.

## WHAT'S DONE (26 items)
- Full VM deployment, Cloudflare tunnels, auto-start
- Hybrid AI (GPT-4o + Claude), TradingView CDP
- 9 sentiment sources, 30-stock watchlist
- Auto-trailing-stops, anti-buyback, ATR sizing
- Earnings reaction, short candidates, macro scanner
- Discord report overhaul (2 clean embeds)
- All 8 scraper/parsing/VWAP fixes
- Dashboard built (needs rebuild on VM after pull)

## 14 REMAINING TODOS (in SQL todos table)
### Bot (4)
- bracket-orders: OCO (buy + stop + target = 1 order)
- correlation-check: Portfolio correlation / beta check
- options-flow: Unusual options activity scanning
- pairs-trading: Long strong + short weak

### Dashboard War Room (7)
- dash-live-sync: WebSocket updates from bot
- dash-runner-tracker: Pre/mid/post-market runners
- dash-sector-heatmap: Visual sector money flow
- dash-trailing-viz: Stop distance visualization
- dash-news-feed: Live headlines with sector tags
- dash-ai-panel: AI reasoning display
- dash-bot-log: Action timeline

### Analytics + Infra (3)
- sharpe-tracking: Sharpe ratio + max drawdown
- dash-mobile: Mobile responsive
- claude-migration: Personal Anthropic API key ($20/mo)

## CURRENT PORTFOLIO (as of Apr 29, 2026 ~4PM ET)
$102,217 equity | 13 positions | Net P&L: -$375
Top winners: DVN (+$126), NOK (+$3), INTC (re-bought)
All positions now have 3% trailing stops
⚠️ META + AMZN + GOOGL had earnings TODAY — check after-hours moves!
