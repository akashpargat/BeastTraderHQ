@echo off
echo ====================================
echo   BEAST ENGINE V3 - Starting All
echo ====================================
set PYTHONIOENCODING=utf-8
cd /d C:\beast-test2

echo Starting Dashboard API (port 8080)...
start "BeastAPI" cmd /c "cd /d C:\beast-test2 && C:\Python312\python.exe dashboard_api.py"

echo Starting Dashboard UI (port 3000)...
start "BeastDash" cmd /c "cd /d C:\beast-test2\dashboard && npx next start -p 3000"

timeout /t 5 /nobreak

echo Starting Discord Bot (autonomous loop)...
C:\Python312\python.exe discord_bot.py
