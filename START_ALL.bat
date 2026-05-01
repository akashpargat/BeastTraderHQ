@echo off
echo ============================================
echo   BEAST TERMINAL V5 - One-Click Startup
echo   %date% %time%
echo ============================================
set PYTHONIOENCODING=utf-8
set PY=C:\Users\beastadmin\AppData\Local\Programs\Python\Python312\python.exe
set LOG=C:\beast-test2\startup.log
cd /d C:\beast-test2

echo [%time%] Starting Beast Terminal V5... > %LOG%
echo [%time%] Starting Beast Terminal V5...

REM ── STEP 1: Kill everything ──
echo.
echo [1/8] Killing old processes...
echo [%time%] STEP 1: Killing old processes >> %LOG%
taskkill /F /IM TradingView.exe 2>>%LOG%
taskkill /F /IM chrome.exe 2>>%LOG%
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "9222" ^| findstr "LISTENING"') do (
    echo [%time%] Killing PID %%a on port 9222 >> %LOG%
    taskkill /F /PID %%a 2>>%LOG%
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "8080" ^| findstr "LISTENING"') do (
    echo [%time%] Killing PID %%a on port 8080 >> %LOG%
    taskkill /F /PID %%a 2>>%LOG%
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "3000" ^| findstr "LISTENING"') do (
    echo [%time%] Killing PID %%a on port 3000 >> %LOG%
    taskkill /F /PID %%a 2>>%LOG%
)
timeout /t 5 /nobreak >nul
echo [%time%] Ports cleared >> %LOG%
echo   Done.

REM ── STEP 2: Verify Python ──
echo.
echo [2/8] Checking Python...
echo [%time%] STEP 2: Checking Python >> %LOG%
%PY% --version >> %LOG% 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   ERROR: Python not found at %PY% >> %LOG%
    echo   ERROR: Python not found at %PY%
    echo   Trying 'py' launcher...
    py --version >> %LOG% 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo   FATAL: No Python found! >> %LOG%
        echo   FATAL: No Python found!
        pause
        exit /b 1
    )
    set PY=py
)
echo   Python OK >> %LOG%
echo   Python OK

REM ── STEP 3: Pull latest code ──
echo.
echo [3/8] Pulling latest code...
echo [%time%] STEP 3: Git pull >> %LOG%
"C:\Program Files\Git\cmd\git.exe" pull origin main --force >> %LOG% 2>&1
echo   Done.

REM ── STEP 4: Install deps ──
echo.
echo [4/8] Installing dependencies...
echo [%time%] STEP 4: Installing deps >> %LOG%
%PY% -m pip install -r requirements.txt --quiet >> %LOG% 2>&1
%PY% -m pip install discord.py openai websocket-client aiohttp flask flask-cors beautifulsoup4 pandas --quiet >> %LOG% 2>&1
echo   Done.

REM ── STEP 5: Start TradingView Desktop ──
echo.
echo [5/8] Starting TradingView Desktop with CDP...
echo [%time%] STEP 5: Starting TradingView >> %LOG%

REM Verify port 9222 is free
netstat -ano | findstr "9222" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   WARNING: Port 9222 still in use! >> %LOG%
    echo   WARNING: Port 9222 still in use!
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr "9222" ^| findstr "LISTENING"') do (
        echo   Killing PID %%a >> %LOG%
        taskkill /F /PID %%a 2>>%LOG%
    )
    timeout /t 3 /nobreak >nul
)

REM Try TradingView Desktop with CDP
set TV_EXE=C:\Program Files\WindowsApps\TradingView.Desktop_3.1.0.7818_x64__n534cwy3pjxzj\TradingView.exe
echo   Launching: "%TV_EXE%" --remote-debugging-port=9222 >> %LOG%
start "" "%TV_EXE%" --remote-debugging-port=9222
if %ERRORLEVEL% NEQ 0 (
    echo   TV Desktop launch returned error %ERRORLEVEL% >> %LOG%
    echo   TV Desktop launch failed, trying explorer... >> %LOG%
    explorer shell:AppsFolder\TradingView.Desktop_n534cwy3pjxzj!TradingView.Desktop
)
echo   Waiting 25s for TV to load...
echo [%time%] Waiting 25s for TV >> %LOG%
timeout /t 25 /nobreak >nul

REM Verify CDP
echo [%time%] Checking CDP on port 9222... >> %LOG%
powershell -Command "try { $r = Invoke-WebRequest http://localhost:9222/json/version -UseBasicParsing -TimeoutSec 5; Write-Output ('CDP OK: ' + $r.Content.Substring(0, [Math]::Min(100, $r.Content.Length))); exit 0 } catch { Write-Output ('CDP FAIL: ' + $_.Exception.Message); exit 1 }" >> %LOG% 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   WARNING: TV CDP not responding on 9222 >> %LOG%
    echo   WARNING: TV CDP not responding! Bot will use headless fallback.
) else (
    echo   TV CDP OK >> %LOG%
    echo   TV CDP connected!
)

REM Check TV targets (chart loaded?)
powershell -Command "try { $r = Invoke-WebRequest http://localhost:9222/json -UseBasicParsing -TimeoutSec 5; $pages = ($r.Content | ConvertFrom-Json); Write-Output ('TV pages: ' + $pages.Count + ' - ' + ($pages | ForEach-Object { $_.title } | Select-Object -First 3 | Join-String -Separator ', ')); exit 0 } catch { Write-Output 'No TV pages'; exit 1 }" >> %LOG% 2>&1

REM ── STEP 6: Setup TV indicators ──
echo.
echo [6/8] Setting up TV indicators...
echo [%time%] STEP 6: TV indicators >> %LOG%
%PY% setup_tv_indicators.py >> %LOG% 2>&1
echo   Done. Check %LOG% for details.

REM ── STEP 7: Start Dashboard API + UI ──
echo.
echo [7/8] Starting Dashboard...
echo [%time%] STEP 7: Dashboard >> %LOG%
start "BeastAPI" cmd /c "cd /d C:\beast-test2 && set PYTHONIOENCODING=utf-8 && %PY% dashboard_api.py >> C:\beast-test2\api.log 2>&1"
echo   API starting on port 8080... >> %LOG%
timeout /t 5 /nobreak >nul

REM Verify API
powershell -Command "try { $r = Invoke-WebRequest http://localhost:8080/api/health -UseBasicParsing -TimeoutSec 5; Write-Output ('API OK: ' + $r.Content); exit 0 } catch { Write-Output ('API FAIL: ' + $_.Exception.Message); exit 1 }" >> %LOG% 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   WARNING: API not responding on 8080 >> %LOG%
    echo   WARNING: Dashboard API failed to start!
) else (
    echo   Dashboard API OK >> %LOG%
    echo   Dashboard API running!
)

start "BeastDash" cmd /c "cd /d C:\beast-test2\dashboard && npx next start -p 3000 >> C:\beast-test2\dash.log 2>&1"
echo   Dashboard UI starting on port 3000...
timeout /t 5 /nobreak >nul

REM ── STEP 8: Start Bot ──
echo.
echo [8/8] Starting Beast Bot...
echo [%time%] STEP 8: Starting bot >> %LOG%
echo ============================================
echo   BEAST TERMINAL V5 - ALL SYSTEMS GO
echo   TV: CDP port 9222
echo   API: port 8080  
echo   Dashboard: port 3000
echo   Bot: autonomous loops starting...
echo   Log: %LOG%
echo   API log: C:\beast-test2\api.log
echo   Dash log: C:\beast-test2\dash.log
echo ============================================
echo.
echo [%time%] ALL SYSTEMS GO >> %LOG%
echo [%time%] Starting discord_bot.py >> %LOG%
%PY% discord_bot.py 2>&1 | tee -a %LOG%
