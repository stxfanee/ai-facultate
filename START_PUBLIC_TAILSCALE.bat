@echo off
setlocal
cd /d "%~dp0"

echo ====================================================
echo Faculty Copilot - acces public prin Tailscale Funnel
echo ====================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_public_tailscale.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" echo Launcherul public nu a fost activat.
pause
exit /b %EXIT_CODE%
