@echo off
setlocal
cd /d "%~dp0\..\.."

call build_server_launcher.bat
exit /b %ERRORLEVEL%
