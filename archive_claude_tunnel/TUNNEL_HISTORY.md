# Beast Engine — Claude Tunnel Architecture (RETIRED)

> **Status**: RETIRED as of V6 (May 2026)
> **Replaced by**: Direct Azure GPT-5.4 + future Azure Foundry Claude
> **Why retired**: Tunnel required work laptop to be ON and UNLOCKED 24/7 — unreliable

---

## What Was the Tunnel?

The Claude tunnel was a Cloudflare-proxied connection from the Azure VM (running the Discord bot)
to Akash's work laptop, which had access to Claude Opus 4.7 via GitHub Copilot API.

```
┌─────────────────┐     HTTPS      ┌──────────────────┐     localhost    ┌─────────────────┐
│   Azure VM      │ ──────────────→│  Cloudflare      │ ──────────────→ │  Work Laptop     │
│   (Discord Bot) │  ai.beast-     │  Tunnel          │  :5555          │  (Flask Server)  │
│                 │  trader.com    │  (Free tier)     │                 │  ai_api_server.py│
│                 │                │                  │                 │       ↓          │
│                 │                │                  │                 │  Claude Opus 4.7 │
│                 │                │                  │                 │  (Copilot API)   │
└─────────────────┘                └──────────────────┘                 └─────────────────┘
```

## Components

### 1. ai_api_server.py (Work Laptop — Flask server)
- Ran on `localhost:5555` on Akash's Microsoft work laptop
- Tiny Flask app exposing 3 endpoints:
  - `GET /health` — status check (no auth)
  - `POST /analyze` — stock analysis via Claude
  - `POST /debate` — bull/bear debate via Claude
  - `POST /briefing` — morning briefing via Claude
- Secured with API key header: `X-API-Key: beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c`
- Instantiated `AIBrain()` locally to access Claude through Copilot

### 2. START_LAPTOP_AI.bat (Work Laptop — Startup script)
- Started `copilot-api` (GitHub Copilot local API server)
- Started `cloudflared tunnel --url http://localhost:5555`
- Cloudflare generated a random URL (e.g., `https://abc123.trycloudflare.com`)
- URL had to be manually copied to VM's `.env` as `AI_API_URL`

### 3. Cloudflare Tunnel (Free tier)
- Domain: `ai.beast-trader.com` (pointed to the tunnel)
- Protocol: HTTP/2 over HTTPS
- No account costs — Cloudflare free tunnel

### 4. VM ai_brain.py (Caller)
- `CLAUDE_URL = os.getenv('AI_API_URL', '')` — the tunnel URL
- `CLAUDE_API_KEY = os.getenv('AI_API_KEY', 'beast-v3-sk-...')` — auth key
- `call_raw()` fallback chain: Claude Direct → Claude Tunnel → GPT Raw
- `analyze_stock()` also had tunnel fallback before V6

## Why It Failed

### Root Cause: Work laptop availability
1. **Laptop locked at night** → Flask server running but Copilot API token expired
   → 3AM Claude learning calls returned EMPTY results every night
2. **Laptop sleep/hibernate** → Cloudflare tunnel disconnected entirely
   → All Claude calls failed with connection refused
3. **VPN disconnects** → Copilot API lost Microsoft auth
   → Server returned 401/500 to VM
4. **Laptop restart** → Had to manually re-run START_LAPTOP_AI.bat
   → Minutes of downtime during trading hours

### Symptoms Observed
- 3AM Claude learning fired successfully (3/3 batches) but GPT returned generic
  verdicts because Claude tunnel was dead and it fell through to GPT
- `brain.analyze_stock('PORTFOLIO', ...)` returned `{action, confidence, reasoning}`
  format instead of custom JSON schema — because it hit GPT fallback, not Claude
- Intermittent "Claude tunnel error: ConnectionError" in logs during market hours
- Dashboard health check showed "tunnel: offline" frequently

### Impact
- Claude was supposed to provide DEEP institutional-grade analysis
- Instead, GPT-5.4 handled everything (which actually worked fine)
- The tunnel added complexity for zero reliability gain

## Environment Variables (RETIRED)

```env
# REMOVED from .env — no longer needed
AI_API_URL=https://ai.beast-trader.com     # Cloudflare tunnel URL
AI_API_KEY=beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c  # Tunnel auth key
```

## Files Removed in V6 Cleanup

| File | Purpose | Why Removed |
|------|---------|-------------|
| `ai_api_server.py` | Flask endpoint on laptop | Tunnel retired |
| `START_LAPTOP_AI.bat` | Start cloudflared + copilot-api | Tunnel retired |

## What Replaced It

### V6 Architecture (Current)
```
Azure VM → Azure GPT-5.4 (East US, "gpt54" deployment)
         → Direct Anthropic API (when ANTHROPIC_API_KEY set)
         → Azure Foundry Claude (when quota approved)
```

- **No laptop dependency** — everything runs server-to-server
- **No Cloudflare** — direct API calls
- **Auto-failover**: `call_raw()` tries Claude Direct → GPT Raw
- **Claude auto-enables**: `CLAUDE_ENABLED = bool(ANTHROPIC_API_KEY)`

### To Enable Claude in Future
1. Get Azure Foundry Anthropic quota (form submitted May 3, 2026)
2. Deploy Claude model on Azure
3. Add `ANTHROPIC_API_KEY=...` to VM `.env`
4. Bot auto-detects and starts using Claude — zero code changes needed

## Local Machine Cleanup (May 3, 2026)

After retiring the tunnel from code, the Cloudflare daemon was still running on the work laptop:

### What Was Found
| Item | State | Details |
|------|-------|---------|
| `cloudflared.exe` | **Running** (PID 6836) | Started Apr 28, 2026 — running 5 days serving nothing |
| Cloudflared Windows Service | **Automatic** start | Would restart on every reboot |
| Service command | `cloudflared tunnel run --token eyJh...` | Persistent tunnel with Cloudflare token |
| Installed at | `C:\Program Files (x86)\cloudflared\cloudflared.exe` | Still installed (not uninstalled) |
| copilot-api | Not running | Was not set up as a service |

### What Was Done
```powershell
# 1. Stop the service
Stop-Service -Name "Cloudflared" -Force

# 2. Disable auto-start (won't run on reboot)
Set-Service -Name "Cloudflared" -StartupType Disabled

# 3. Verified: process killed, no tunnel processes running
Get-Service -Name "Cloudflared"  # → Stopped, Disabled
```

### To Re-enable (if ever needed)
```powershell
Set-Service -Name "Cloudflared" -StartupType Automatic
Start-Service -Name "Cloudflared"
```

### To Fully Uninstall (optional, not done)
```powershell
# Remove the service registration
cloudflared service uninstall

# Then uninstall via Programs & Features or:
# Remove-Item "C:\Program Files (x86)\cloudflared" -Recurse -Force
```

### Cloudflare Account
- The Cloudflare account may still have the tunnel and `beast-trader.com` domain configured
- Login at https://dash.cloudflare.com to clean up if desired
- Tunnels can be deleted from: Zero Trust → Networks → Tunnels
- Domain can be removed from: Websites → beast-trader.com → Remove

---

## How to Rebuild the Tunnel From Scratch (if ever needed)

### Step 1: Work Laptop — Install & Configure Cloudflared
```powershell
# Install cloudflared (if uninstalled)
winget install Cloudflare.cloudflared

# Login to Cloudflare (opens browser)
cloudflared tunnel login

# Create a new tunnel
cloudflared tunnel create beast-ai

# Note the tunnel ID and credentials file path it outputs
# e.g., Tunnel ID: abc123-def456-...
# Credentials: C:\Users\<you>\.cloudflared\abc123-def456.json
```

### Step 2: Work Laptop — Start the AI API Server
```powershell
# Install dependencies
cd C:\OneBranch\Beast-Trader\archive_claude_tunnel
pip install flask python-dotenv openai anthropic

# Start the Flask AI server
python ai_api_server.py
# Should show: 🧠 AI API Server starting on port 5555...
# Test: curl http://localhost:5555/health
```

### Step 3: Work Laptop — Start the Tunnel
```powershell
# Option A: Quick tunnel (random URL, no domain needed)
cloudflared tunnel --url http://localhost:5555

# Option B: Named tunnel with custom domain
cloudflared tunnel route dns beast-ai ai.beast-trader.com
cloudflared tunnel run beast-ai

# Option C: Install as Windows service (auto-start on reboot)
cloudflared service install
# Then configure in: C:\Users\<you>\.cloudflared\config.yml
```

### Step 4: VM — Update .env
```env
# Add these to the VM's .env file
AI_API_URL=https://ai.beast-trader.com    # or the random tunnel URL
AI_API_KEY=beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c
```

### Step 5: Code — Restore Tunnel Fallback in ai_brain.py
```python
# Add back to top of ai_brain.py:
CLAUDE_URL = os.getenv('AI_API_URL', '')
CLAUDE_API_KEY = os.getenv('AI_API_KEY', '')

# Add back to call_raw() after Claude Direct try block:
# Try 2: Claude Tunnel (legacy proxy)
if self._claude_available and not self._claude_direct:
    try:
        resp = requests.post(
            f"{CLAUDE_URL}/analyze",
            json={'prompt': prompt, 'system_prompt': system},
            headers={'X-API-Key': CLAUDE_API_KEY, 'Content-Type': 'application/json'},
            timeout=timeout)
        if resp.status_code == 200:
            result = resp.json()
            return result
    except Exception as e:
        log.warning(f"Claude tunnel error: {e}")
```

### Step 6: Verify End-to-End
```bash
# From VM, test the tunnel:
curl -X POST https://ai.beast-trader.com/analyze \
  -H "X-API-Key: beast-v3-sk-7f3a9e2b4d1c8f5e6a0b3d9c" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
```

### ⚠️ Remember Why We Retired This
- Laptop must be ON, UNLOCKED, and VPN-connected 24/7
- 3AM learning will fail if laptop sleeps
- Cloudflare free tunnel URLs change on restart (unless using named tunnel)
- Much better alternative: Direct Anthropic API or Azure Foundry Claude

---

*Document created: May 3, 2026 — before removing tunnel code from codebase*
*Updated: May 3, 2026 — local machine cleanup + full rebuild guide documented*
