@echo off
setlocal
cd /d "%~dp0\..\.."

call scripts\legacy\build_copilot_facultate.bat
exit /b %ERRORLEVEL%
