@echo off
echo Adding TradingView indicators...
set PY=C:\Users\beastadmin\AppData\Local\Programs\Python\Python312\python.exe
cd /d C:\beast-test2
%PY% setup_tv_indicators.py
pause
