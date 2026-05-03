@echo off
reg add "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v BeastEngine /d "C:\beast-test2\start_beast.bat" /f
reg add "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v TradingViewChrome /d "C:\beast-test2\START_CHROME_TV.bat" /f
echo AUTO-START CONFIGURED
reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v BeastEngine
reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v TradingViewChrome
pause
