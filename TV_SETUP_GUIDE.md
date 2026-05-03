# TradingView Setup Guide — Beast Trading Bot

## Why Chrome Instead of TV Desktop?

The Azure VM runs **Windows Server** which has no Microsoft Store. TradingView Desktop
is an MSIX app that requires the Store for proper installation. Even when installed,
the Electron app's `--remote-debugging-port` flag is unreliable on Windows Server
(JavaScript errors, permission issues, empty CDP targets).

**Solution:** Run TradingView in **Google Chrome** with remote debugging enabled.
The bot's `tv_cdp_client.py` connects to port 9222 — it doesn't care if it's
Chrome or TV Desktop. This is also how the developer's local machine works.

---

## One-Time Setup (only do this once per VM)

### Step 1: Launch Chrome with CDP + dedicated profile

Open a command prompt on the VM (via RDP) and run:

```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\beast-tv-profile --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --disable-features=CalculateNativeWinOcclusion --no-first-run https://www.tradingview.com/chart/
```

Or just double-click `START_CHROME_TV.bat`.

### Step 2: Log in to TradingView Premium

In the Chrome window that opens:
1. Click **Sign In** (top right)
2. Log in with your TradingView Premium account
3. Wait for a chart to load

### Step 3: Add indicators

Press `/` to open indicator search, then add each:
- `Relative Strength Index` (RSI)
- `MACD`
- `VWAP` (Volume Weighted Average Price)
- `Bollinger Bands`
- `Moving Average Exponential` — add TWICE (set periods to 9 and 21)
- `Ichimoku Cloud` (optional but used by Guru Shopping)

OR run the auto-setup script (in a separate terminal):
```cmd
cd C:\beast-test2
C:\Python312\python.exe setup_tv_indicators.py
```

### Step 4: Save the layout

Press **Ctrl+S** to save. The layout persists in `C:\beast-tv-profile\` so 
indicators survive Chrome restarts.

### Step 5: Verify CDP works

```cmd
powershell "(Invoke-WebRequest http://localhost:9222/json/version -UseBasicParsing).Content"
```

Should show: `"Browser": "Chrome/..."` and the TradingView version.

```cmd
powershell "(Invoke-WebRequest http://localhost:9222/json -UseBasicParsing).Content"
```

Should show at least one page with `tradingview.com/chart` in the URL.

---

## Daily Operations

### Starting the bot (TV already running)

```cmd
cd C:\beast-test2
START_ALL.bat
```

START_ALL.bat does NOT touch TV/Chrome — it assumes TV is already running on 9222.
It only starts: API (8080), Dashboard (3000), Discord Bot.

### If TV Chrome died (VM restarted, Chrome crashed)

```cmd
START_CHROME_TV.bat
```

Wait for Chrome to load TradingView (it auto-loads your saved chart + indicators
because the profile is persisted at `C:\beast-tv-profile\`).

Then run `START_ALL.bat`.

### If indicators are missing after restart

The Chrome profile saves your TV session. But if indicators disappear:

```cmd
cd C:\beast-test2
C:\Python312\python.exe setup_tv_indicators.py
```

---

## Troubleshooting

### "CDP not responding on port 9222"
1. Check if Chrome is running: `tasklist | findstr chrome`
2. Check port: `netstat -ano | findstr 9222`
3. If port is in use but Chrome shows no TV pages: kill and relaunch
   ```cmd
   taskkill /F /IM chrome.exe
   START_CHROME_TV.bat
   ```

### "TV: only 1 study after retries — insufficient"
Indicators not loaded. Either:
- You're not logged into TV Premium (free accounts have indicator limits)
- Indicators weren't saved — add them and press Ctrl+S
- Run `setup_tv_indicators.py`

### "Access denied" when launching TV Desktop
This is the MSIX/Windows Server issue. Don't use TV Desktop — use Chrome instead.
Run `START_CHROME_TV.bat`.

### Python "Access denied" or 0-byte python.exe
The `C:\Python312\python.exe` got corrupted. Fix:
```cmd
copy "C:\Users\beastadmin\AppData\Local\Programs\Python\Python312\python.exe" "C:\Python312\python.exe"
```

---

## Architecture

```
Chrome (port 9222)                 Bot (discord_bot.py)
┌─────────────────┐              ┌──────────────────────┐
│ TradingView.com │◄─── CDP ────►│ tv_cdp_client.py     │
│ + 7 indicators  │  WebSocket   │ _get_tv_indicators() │
│ + Premium login │              │ _tv_confirm_buy()    │
└─────────────────┘              └──────────────────────┘
Profile: C:\beast-tv-profile\     Falls back to:
                                  headless_technicals.py
                                  (computes RSI/MACD/etc
                                   from Alpaca bar data)
```

## Files

| File | Purpose |
|------|---------|
| `START_CHROME_TV.bat` | Launch Chrome with TV + CDP on port 9222 |
| `START_ALL.bat` | Start API + Dashboard + Bot (assumes TV running) |
| `setup_tv_indicators.py` | Auto-add RSI/MACD/VWAP/BB/EMA to chart via CDP |
| `tv_cdp_client.py` | WebSocket client that reads indicators from Chrome |
| `headless_technicals.py` | Fallback: compute indicators from Alpaca data |
| `TV_SETUP_GUIDE.md` | This file |
