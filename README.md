# 🦍 Beast Engine v3.0 — CLOUD EDITION

## Status: 🔨 PLANNING

## The Setup

```
YOUR WORK LAPTOP                     AZURE VM ($30/mo from $150 credit)
━━━━━━━━━━━━━━━━                     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 AI Brain ONLY                     EVERYTHING ELSE (24/7):
  ai_api_server.py                    📺 TradingView Web (Chrome + CDP)
  copilot-api → Claude Opus 4.7       🔌 Alpaca API (trading)
  Cloudflare Tunnel (free)            📰 5 sentiment sources
  Works when LOCKED ✅                🎯 Confidence Engine
                                      ⛔ Iron Laws (hardcoded)
         ↕ HTTPS ↕                    🔍 Sector Scanner (48 stocks)
                                      📊 Monitor (trailing stops)
                                      🎮 Discord Bot (24+ commands)
                                      📱 Telegram Alerts
                                      🔬 Backtesting (TV data)
                                      📈 Performance Tracker
                                      🤖 AUTO LOOP (g every 60s)
                                      🌅 Pre-market scanner (4 AM)
                                      🌙 Post-market scanner (4 PM)
                                      💾 SQLite trade database
                                      📊 Daily/weekly reports
```

## What We Need

### Azure VM
- **Size**: B2ms (2 CPU, 8 GB RAM) — $30/month
- **OS**: Windows 11 (needed for Chrome + TradingView Web)
- **Storage**: 128 GB SSD
- **Network**: Public IP + RDP access
- **Auto-start**: VM boots → services start → bot runs

### Software on VM
- Python 3.14+
- Node.js 20+
- Google Chrome (for TradingView Web + CDP)
- Git (clone beast-v3)
- All Python packages (requirements.txt)

### Accounts Needed (all on VM)
- **Alpaca**: Paper trading API keys (same as now)
- **TradingView**: Log into Premium in Chrome on VM
- **Discord**: Bot token (same @BeastTrader#5020)
- **Telegram**: Bot token (same @KashKingTraderBot)
- **Cloudflare**: Free account for tunnel

### On Work Laptop (minimal)
- copilot-api (already installed)
- ai_api_server.py (already built)
- cloudflared (free CLI tool)
- Start 2 commands and forget

## V3 Build Phases

### Phase 1: Azure VM Setup
- [ ] Create VM (B2ms, Windows, RDP)
- [ ] Install Python, Node, Chrome, Git
- [ ] Clone beast-v3 code
- [ ] pip install -r requirements.txt
- [ ] Set up .env with all API keys
- [ ] Test Alpaca connection
- [ ] Log into TradingView Premium in Chrome
- [ ] Add all indicators to TV chart
- [ ] Test TV CDP from Chrome on VM
- [ ] Test Discord bot from VM
- [ ] Test Telegram from VM

### Phase 2: AI Bridge
- [ ] Install cloudflared on work laptop
- [ ] Create tunnel: cloudflared tunnel create beast-ai
- [ ] Route tunnel to localhost:5555
- [ ] Update VM .env with tunnel URL
- [ ] Test AI calls from VM → laptop
- [ ] Test with laptop locked
- [ ] Add auto-reconnect logic
- [ ] Add deterministic fallback

### Phase 3: Autonomous Loop
- [ ] Wire beast_mode_loop.py with VM's TV Chrome
- [ ] Configure semi-auto mode (>80% auto, 60-80% ask)
- [ ] Add pre-market scanner (4:00 AM ET)
- [ ] Add market hours loop (9:30-4:00 PM, every 60s)
- [ ] Add post-market scanner (4:00-8:00 PM)
- [ ] Add overnight monitor (8 PM - 4 AM, every 30 min)
- [ ] Add daily report auto-send (4:30 PM)
- [ ] Add weekly report (Friday 5 PM)

### Phase 4: Reliability
- [ ] Windows Service (auto-start on VM boot)
- [ ] Crash watchdog (restart on failure)
- [ ] Health check alerts (if bot dies → Telegram alert)
- [ ] Trade DB backup (daily to Azure Blob)
- [ ] Error rate monitoring
- [ ] AI reconnection loop (retry every 5 min)

### Phase 5: Advanced
- [ ] Pre-market gap scanner with alerts
- [ ] Earnings calendar auto-fetch weekly
- [ ] Strategy auto-optimizer (run weekly)
- [ ] Performance report dashboard
- [ ] Multi-timeframe analysis (1min + 5min + daily)

## Cost Summary
| Item | Monthly | From Credits |
|------|---------|-------------|
| Azure VM (B2ms) | $30 | ✅ $150 credit |
| TradingView Premium | $0 | Already have |
| Alpaca Paper | $0 | Free |
| Cloudflare Tunnel | $0 | Free |
| Discord Bot | $0 | Free |
| Telegram Bot | $0 | Free |
| AI (copilot-api) | $0 | Via work laptop |
| **TOTAL** | **$30/mo** | **5 months free** |
