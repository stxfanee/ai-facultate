@echo off
setlocal
cd /d "%~dp0"

echo ====================================================
echo Co-pilot Facultate - Cloudflare Tunnel public HTTPS
echo ====================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_cloudflare_tunnel.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" echo Cloudflare Tunnel nu a fost pornit.
pause
exit /b %EXIT_CODE%
