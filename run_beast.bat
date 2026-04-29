@echo off
echo =============================================
echo   BEAST ENGINE v2.0 - Starting...
echo =============================================
cd /d "%~dp0"
python run_beast.py %*
pause
