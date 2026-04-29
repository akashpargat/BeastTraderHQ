# UNIFIED UPDATE PROTOCOL — The Learning Pipeline
# ================================================
# When we learn ANYTHING new, it gets pushed to ALL 7 locations.
# No more scattered knowledge. No more rookie sessions missing lessons.
# Created: 2026-04-28 by Session 7a05060d
#
# TRIGGER: After every mistake, win, new rule, or strategy discovery
#
# THE 7 UPDATE TARGETS (in order):
#
# 1. memory/learnings.md          — Human-readable lessons + Iron Laws
# 2. memory/strategy_state.md     — Current positions, account, regime
# 3. memory/beast_mode_protocol.md — "g" protocol phases
# 4. memory/SESSION_RULES.md      — Multi-session coordination rules
# 5. .github/copilot-instructions.md — Auto-load for new CLI sessions
# 6. AI_DAY_TRADER_SKILL.md       — Master playbook (header + strategies)
# 7. beast-v3/iron_laws.py        — HARDCODED Python enforcement in bot
#    beast-v3/beast_mode_loop.py   — Watchlists, sectors, scan logic
#    beast-v3/sector_scanner.py    — Sector definitions
#    beast-v3/sentiment_analyst.py — Sentiment keywords
#
# WHAT GETS UPDATED WHERE:
#
# ┌─────────────────────┬───┬───┬───┬───┬───┬───┬───┐
# │ LESSON TYPE         │ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │ 7 │
# ├─────────────────────┼───┼───┼───┼───┼───┼───┼───┤
# │ New Iron Law        │ ✅│   │   │ ✅│ ✅│ ✅│ ✅│
# │ New Strategy        │ ✅│   │ ✅│   │ ✅│ ✅│ ✅│
# │ Trade mistake       │ ✅│   │   │ ✅│   │   │   │
# │ Trade win           │ ✅│   │   │   │   │   │   │
# │ Position change     │   │ ✅│   │   │   │   │   │
# │ New stock/sector    │ ✅│   │ ✅│   │   │   │ ✅│
# │ Protocol change     │   │   │ ✅│ ✅│ ✅│   │ ✅│
# │ Past winner added   │ ✅│   │ ✅│ ✅│ ✅│   │ ✅│
# │ Sentiment keyword   │   │   │   │   │   │   │ ✅│
# │ Session backup      │   │   │   │   │   │   │   │
# └─────────────────────┴───┴───┴───┴───┴───┴───┴───┘
#
# EXAMPLE: We learn "don't chase +5% stocks" (Rule #29)
#
# 1. learnings.md       → Add Rule #29 with story + $ cost
# 2. strategy_state.md  → (no change)
# 3. beast_mode_protocol → Add to "Common Mistakes" section
# 4. SESSION_RULES.md   → Add to rookie mistakes list
# 5. copilot-instructions → Add to CRITICAL RULES
# 6. AI_DAY_TRADER_SKILL → (only if major strategy change)
# 7. iron_laws.py       → Add law_29_no_chase() function
#    beast_mode_loop.py → (if affects scan logic)
#
# HOW TO TRIGGER AN UPDATE:
#
# During a session, say:
#   "Update all files with [lesson]"
#   or just describe the lesson and I'll push everywhere
#
# At end of day, say:
#   "Update all memory files for today"
#   and I'll do a full sync of positions, lessons, state
#
# The bot on the VM will pick up changes to beast-v3/ automatically
# if it's running from the OneDrive-synced folder.
# Memory files are read by new Copilot sessions on startup.
