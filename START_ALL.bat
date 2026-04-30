@echo off
echo ============================================
echo   BEAST TERMINAL V4 - Full Setup + Start
echo ============================================
set PYTHONIOENCODING=utf-8
cd /d C:\beast-test2

echo.
echo [1/7] Pulling latest code from GitHub...
"C:\Program Files\Git\cmd\git.exe" pull origin main --force
echo Waiting 5s...
timeout /t 5 /nobreak >nul

echo.
echo [2/7] Installing Python dependencies...
C:\Python312\python.exe -m pip install psycopg2-binary --quiet 2>nul
echo Done.

echo.
echo [3/7] Rebuilding Dashboard (Next.js)...
cd /d C:\beast-test2\dashboard
if exist .next rd /s /q .next
call npm install --silent 2>nul
call npx next build 2>nul
cd /d C:\beast-test2
echo Dashboard built.

echo.
echo [4/7] Starting TradingView Desktop with CDP...
start "" "C:\Program Files\WindowsApps\TradingView.Desktop_3.1.0.7818_x64__n534cwy3pjxzj\TradingView.exe" --remote-debugging-port=9222
echo Waiting 20s for TV to load chart...
timeout /t 20 /nobreak >nul

echo.
echo [5/7] Starting Dashboard API (port 8080)...
start "BeastAPI" cmd /c "cd /d C:\beast-test2 && set PYTHONIOENCODING=utf-8 && C:\Python312\python.exe dashboard_api.py"
echo Waiting 5s...
timeout /t 5 /nobreak >nul

echo.
echo [6/7] Starting Dashboard UI (port 3000)...
start "BeastDash" cmd /c "cd /d C:\beast-test2\dashboard && npx next start -p 3000"
echo Waiting 10s...
timeout /t 10 /nobreak >nul

echo.
echo [7/7] Starting Discord Bot (autonomous trading)...
echo ============================================
echo   ALL SYSTEMS GO - Beast Terminal V4
echo   TV: CDP port 9222
echo   API: port 8080
echo   Dashboard: port 3000
echo   Bot: autonomous loops starting...
echo   PostgreSQL: Azure beast-trading-db
echo ============================================
echo.
C:\Python312\python.exe discord_bot.py
