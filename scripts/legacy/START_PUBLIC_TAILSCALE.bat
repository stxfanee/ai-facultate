@echo off
setlocal
cd /d "%~dp0\..\.."

echo ====================================================
echo Co-pilot Facultate - acces public prin Tailscale Funnel
echo ====================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\deployment\start_public_tailscale.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" echo Launcherul public nu a fost activat.
pause
exit /b %EXIT_CODE%
