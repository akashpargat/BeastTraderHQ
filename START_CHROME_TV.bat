@echo off
echo Starting Chrome with TradingView (anti-throttle mode)...
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9222 ^
    --disable-background-timer-throttling ^
    --disable-backgrounding-occluded-windows ^
    --disable-renderer-backgrounding ^
    --disable-features=CalculateNativeWinOcclusion ^
    --no-first-run ^
    https://www.tradingview.com/chart
