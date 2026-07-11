@echo off
setlocal
cd /d "%~dp0\..\.."

call scripts\legacy\START_CLOUDFLARE_TUNNEL.bat
exit /b %ERRORLEVEL%
