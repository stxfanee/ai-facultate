@echo off
setlocal
cd /d "%~dp0\..\.."

call scripts\legacy\build_desktop_client.bat
exit /b %ERRORLEVEL%
