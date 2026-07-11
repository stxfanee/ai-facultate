@echo off
setlocal
cd /d "%~dp0\..\.."

call scripts\legacy\build_server_launcher.bat
exit /b %ERRORLEVEL%
