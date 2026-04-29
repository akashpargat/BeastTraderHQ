@echo off
echo ====================================
echo   BEAST ENGINE V3 - Starting All
echo ====================================
set PYTHONIOENCODING=utf-8
cd /d C:\beast-test2

echo Starting TradingView Desktop with CDP...
start "" "C:\Program Files\WindowsApps\TradingView.Desktop_3.1.0.7818_x64__n534cwy3pjxzj\TradingView.exe" --remote-debugging-port=9222

echo Waiting for TradingView to load...
timeout /t 15 /nobreak

echo Starting Dashboard API (port 8080)...
start "BeastAPI" cmd /c "cd /d C:\beast-test2 && C:\Python312\python.exe dashboard_api.py"

echo Starting Dashboard UI (port 3000)...
start "BeastDash" cmd /c "cd /d C:\beast-test2\dashboard && npx next start -p 3000"

timeout /t 5 /nobreak

echo Starting Discord Bot (autonomous loop)...
C:\Python312\python.exe discord_bot.py
