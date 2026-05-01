@echo off
echo ============================================
echo   BEAST TERMINAL V5 - One-Click Startup
echo   %date% %time%
echo ============================================
echo.
echo   NOTE: TradingView Chrome must already be running!
echo   If not, run START_CHROME_TV.bat first.
echo.
set PYTHONIOENCODING=utf-8
set PY=C:\Users\beastadmin\AppData\Local\Programs\Python\Python312\python.exe
set LOG=C:\beast-test2\startup.log
cd /d C:\beast-test2

echo [%time%] Starting Beast Terminal V5... > %LOG%

REM ── STEP 1: Verify Python ──
echo [1/6] Checking Python...
echo [%time%] STEP 1: Checking Python >> %LOG%
%PY% --version >> %LOG% 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   ERROR: Python not found at %PY%
    echo   Trying py launcher...
    py --version >> %LOG% 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo   FATAL: No Python found!
        pause
        exit /b 1
    )
    set PY=py
)
echo   Python OK

REM ── STEP 2: Pull latest code ──
echo [2/6] Pulling latest code...
echo [%time%] STEP 2: Git pull >> %LOG%
"C:\Program Files\Git\cmd\git.exe" pull origin main --force >> %LOG% 2>&1
echo   Done.

REM ── STEP 3: Install deps ──
echo [3/6] Installing dependencies...
echo [%time%] STEP 3: Installing deps >> %LOG%
%PY% -m pip install -r requirements.txt --quiet >> %LOG% 2>&1
%PY% -m pip install discord.py openai websocket-client aiohttp flask flask-cors beautifulsoup4 pandas --quiet >> %LOG% 2>&1
echo   Done.

REM ── STEP 4: Verify TV CDP is running ──
echo [4/6] Checking TradingView CDP...
echo [%time%] STEP 4: TV CDP check >> %LOG%
powershell -Command "try { $r = Invoke-WebRequest http://localhost:9222/json/version -UseBasicParsing -TimeoutSec 5; Write-Output ('CDP OK: ' + $r.Content.Substring(0, [Math]::Min(80, $r.Content.Length))); exit 0 } catch { Write-Output 'CDP NOT RESPONDING'; exit 1 }" >> %LOG% 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   WARNING: TV CDP not responding on port 9222!
    echo   Run START_CHROME_TV.bat first, log into TV, then re-run this script.
    echo   See TV_SETUP_GUIDE.md for instructions.
    echo [%time%] WARNING: TV CDP not responding >> %LOG%
) else (
    echo   TV CDP connected!
    echo [%time%] TV CDP OK >> %LOG%
)

REM ── STEP 5: Start Dashboard API + UI ──
echo [5/6] Starting Dashboard...
echo [%time%] STEP 5: Dashboard >> %LOG%

REM Kill old API/Dashboard if running
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "8080" ^| findstr "LISTENING"') do (
    echo   Killing old API on PID %%a >> %LOG%
    taskkill /F /PID %%a 2>>%LOG%
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "3000" ^| findstr "LISTENING"') do (
    echo   Killing old Dashboard on PID %%a >> %LOG%
    taskkill /F /PID %%a 2>>%LOG%
)
timeout /t 3 /nobreak >nul

start "BeastAPI" cmd /c "cd /d C:\beast-test2 && set PYTHONIOENCODING=utf-8 && %PY% dashboard_api.py >> C:\beast-test2\api.log 2>&1"
echo   API starting on port 8080...
timeout /t 5 /nobreak >nul

powershell -Command "try { $r = Invoke-WebRequest http://localhost:8080/api/health -UseBasicParsing -TimeoutSec 5; Write-Output ('API OK: ' + $r.Content); exit 0 } catch { Write-Output 'API FAIL'; exit 1 }" >> %LOG% 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   WARNING: Dashboard API failed to start!
) else (
    echo   Dashboard API running!
)

start "BeastDash" cmd /c "cd /d C:\beast-test2\dashboard && npx next start -p 3000 >> C:\beast-test2\dash.log 2>&1"
echo   Dashboard UI starting on port 3000...
timeout /t 5 /nobreak >nul

REM ── STEP 6: Start Bot ──
echo [6/6] Starting Beast Bot...
echo [%time%] STEP 6: Starting bot >> %LOG%
echo ============================================
echo   BEAST TERMINAL V5 - ALL SYSTEMS GO
echo   TV: CDP port 9222 (must be running already)
echo   API: port 8080
echo   Dashboard: port 3000
echo   Bot: autonomous loops starting...
echo   Log: %LOG%
echo ============================================
echo.
echo [%time%] Starting discord_bot.py >> %LOG%
%PY% discord_bot.py
