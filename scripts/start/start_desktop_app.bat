@echo off
setlocal
cd /d "%~dp0\..\.."

if exist "dist\Co-pilot Facultate.exe" (
    start "" "dist\Co-pilot Facultate.exe"
    exit /b 0
)

echo dist\Co-pilot Facultate.exe not found.
echo Build it first with scripts\build\build_desktop_app.bat
exit /b 1
