@echo off
setlocal
cd /d "%~dp0\..\.."

call scripts\build\build_desktop_app.bat
if errorlevel 1 exit /b 1

call scripts\build\build_server_launcher.bat
if errorlevel 1 exit /b 1

call scripts\build\build_client.bat
if errorlevel 1 exit /b 1

echo.
echo All build artifacts are in dist\
exit /b 0
