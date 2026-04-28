@echo off
reg add "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v BeastEngine /d "C:\beast-test2\start_beast.bat" /f
reg add "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v TradingView /d "C:\Users\beastadmin\AppData\Local\Microsoft\WindowsApps\TradingView.exe" /f
echo AUTO-START CONFIGURED
reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v BeastEngine
reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v TradingView
pause
