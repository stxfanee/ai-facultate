@echo off
setlocal
cd /d "%~dp0\..\.."

call scripts\legacy\start_server.bat
exit /b %ERRORLEVEL%
