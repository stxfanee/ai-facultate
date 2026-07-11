@echo off
setlocal
cd /d "%~dp0\..\.."

call build_desktop_client.bat
exit /b %ERRORLEVEL%
