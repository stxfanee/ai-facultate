@echo off
setlocal
cd /d "%~dp0\..\.."

call START_CLOUDFLARE_TUNNEL.bat
exit /b %ERRORLEVEL%
