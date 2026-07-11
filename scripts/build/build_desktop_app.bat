@echo off
setlocal
cd /d "%~dp0\..\.."

call build_copilot_facultate.bat
exit /b %ERRORLEVEL%
