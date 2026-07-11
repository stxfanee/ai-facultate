@echo off
setlocal
cd /d "%~dp0\..\.."

call start_server.bat
exit /b %ERRORLEVEL%
