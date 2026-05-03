@echo off
REM Start copilot-api + cloudflared tunnel on work laptop
REM Run this once when you start your laptop

echo Starting copilot-api...
start /b copilot-api start

timeout /t 5 /nobreak

echo Starting Cloudflare tunnel...
REM This outputs the URL to a file, then we update the VM
cloudflared tunnel --url http://localhost:5555 --protocol http2 2>&1 | findstr "https://" > C:\Users\%USERNAME%\tunnel_url.txt

echo Tunnel started. Check tunnel_url.txt for the URL.
echo Update VM .env with: AI_API_URL=<tunnel_url>
pause
