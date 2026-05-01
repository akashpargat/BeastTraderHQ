@echo off
echo =============================================
echo   BEAST ENGINE v2.0 - Starting...
echo =============================================
set PY=C:\Users\beastadmin\AppData\Local\Programs\Python\Python312\python.exe
cd /d "%~dp0"
%PY% run_beast.py %*
pause
