@echo off
setlocal
cd /d "%~dp0\..\.."

call scripts\start\start_desktop_app.bat
exit /b %ERRORLEVEL%
