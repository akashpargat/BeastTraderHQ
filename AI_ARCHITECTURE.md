# 🧠 Beast Bot — AI Architecture & Configuration Guide

## Current Setup (V6)

### AI Models
| Model | Usage | Status |
|-------|-------|--------|
| **Azure GPT-5.4** | ALL scans (5-min, 30-min, 1hr, 3AM) | ✅ Active |
| **Claude (Anthropic)** | Placeholder — future enhancement | ⏳ Disabled |

### Why GPT-5.4 Only?
- Azure GPT-5.4 (`gpt54` deployment) handles everything reliably
- Claude tunnel (`ai.beast-trader.com`) was unreliable — removed
- Direct Anthropic API code is ready but key not purchased yet
- Need 2+ weeks of token tracking data before estimating Claude costs

---

## Branch Strategy

```
main
  └── feature/beast-v5-pro-upgrades  ← VM RUNS THIS (stable, proven)
        └── feature/beast-v6-direct-claude  ← AI upgrades (test here first)
```

**Rule: NEVER modify v5-pro-upgrades for AI changes. All AI work on v6-direct-claude.**

When v6 is tested and ready → merge into v5 → deploy to VM.

---

## AI Call Points (discord_bot.py)

| Task Loop | Frequency | What it does | AI Method |
|-----------|-----------|-------------|-----------|
| `full_scan` | Every 5 min | Analyze 16 stocks for BUY/HOLD/SELL | `brain.analyze_batch()` |
| `claude_deep_scan` | Every 30 min | Deep analysis on 8 stocks | `brain.deep_analyze()` |
| `ai_background_learning` | Every 1 hr | Learn patterns on 20 watchlist stocks | `brain.analyze_stock()` |
| `claude_daily_deep_learn` | Daily 3 AM ET | 3 batched learning calls | `brain.call_raw()` |
| Discord commands (`!scan`, `!ai`) | On demand | User-triggered analysis | `brain.analyze_stock()` |

### 3AM Deep Learning (Batched)
3 separate AI calls, 5s pause between each:
1. **"market"** — Buy/avoid list, sector analysis (~2K tokens)
2. **"exits"** — Scalp/trail adjustments from sell data (~1.8K tokens)
3. **"intelligence"** — Stock DNA, earnings, catalysts (~2K tokens)

Results merged and saved to `ai_trends` table as daily playbook.

---

## Token Tracking

### How it works
Every GPT call tracks `tokens_in` + `tokens_out` in `_ai_stats`:
- Single stock: `_gpt_analyze()` → logs per-call tokens
- Batch (16 stocks): `analyze_batch()` → logs batch tokens
- 3AM raw: `call_raw()` → logs with daily running total

### Where to see it
- **Console logs**: `daily_total=X tokens` after each call
- **ai_verdicts.data**: Each verdict has `tokens_used`, `tokens_in`, `tokens_out`
- **brain.get_token_stats()**: Returns session totals + estimated USD cost

### Estimated monthly costs (from actual usage data)
```
GPT-5.4 only (current):     ~$0/mo (Azure subscription covers it)
+ Claude Sonnet for scans:  ~$77/mo
+ Claude Opus for 3AM:      ~$3/mo
Full Claude (all scans):    ~$129/mo (Opus) or ~$77/mo (Sonnet)
```

---

## Enabling Claude (Future)

### Step 1: Get API Key
1. Go to https://console.anthropic.com/
2. Create account, add payment
3. Generate API key (`sk-ant-...`)

### Step 2: Add to Environment
```bash
# On VM (.env or system env):
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx

# Bot auto-detects: CLAUDE_ENABLED = bool(ANTHROPIC_API_KEY)
```

### Step 3: Verify
Bot startup will show:
```
🧠 Claude ONLINE — Direct Anthropic API (claude-sonnet-4-20250514)
```
Instead of:
```
🧠 Claude DISABLED — GPT-only mode (set ANTHROPIC_API_KEY to enable)
```

### Step 4: Choose Model
Set in `.env`:
```bash
CLAUDE_MODEL=claude-sonnet-4-20250514    # $3/$15 per MTok (recommended)
# or
CLAUDE_MODEL=claude-opus-4-20250514      # $5/$25 per MTok (smartest)
# or  
CLAUDE_MODEL=claude-haiku-3-5-20241022   # $0.80/$4 per MTok (cheapest)
```

---

## Key Files

| File | Purpose |
|------|---------|
| `ai_brain.py` | AI engine — GPT-5.4 + Claude placeholder + `call_raw()` |
| `discord_bot.py` | All task loops that call AI |
| `smart_exits.py` | V6 smart exit engine (uses AI recommendations from 3AM) |
| `intelligence_engine.py` | Stock DNA profiler, earnings analyzer (feeds to 3AM) |
| `.env` | API keys (ANTHROPIC_API_KEY goes here) |

## Database Tables for AI

| Table | What |
|-------|------|
| `ai_verdicts` | Every AI BUY/HOLD/SELL verdict with tokens_used |
| `ai_trends` | Learned patterns: stock_dna, strategy_scores, daily_playbook |
| `activity_log` | DAILY_LEARN_BATCH, DAILY_LEARN_RESPONSE, INTELLIGENCE |
| `trade_log` | Graded trades with pnl_1h/4h/lesson_learned |
| `sell_outcomes` | Post-sell price tracking (premature sell detection) |
