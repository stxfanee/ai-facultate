@echo off
setlocal
cd /d "%~dp0\..\.."

echo Build legacy Co-pilot Facultate lightweight client.
echo The flagship app is built with scripts\build\build_desktop_app.bat.
echo.

set "APP_DIR=apps\legacy_client"
set "BUILD_ENV=%APP_DIR%\.venv_build"
set "APP_ENTRY=%APP_DIR%\launcher.py"
set "CLIENT_ICON=%CD%\%APP_DIR%\assets\copilot_facultate.ico"

if not exist "%APP_ENTRY%" (
    echo Missing %APP_ENTRY%.
    if not defined CI pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_FOR_BUILD=.venv\Scripts\python.exe"
) else (
    set "PYTHON_FOR_BUILD=python"
)

if not exist "%BUILD_ENV%\Scripts\python.exe" (
    "%PYTHON_FOR_BUILD%" -m venv "%BUILD_ENV%"
    if errorlevel 1 exit /b 1
)

"%BUILD_ENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%BUILD_ENV%\Scripts\python.exe" -m pip install pyinstaller pywebview
if errorlevel 1 exit /b 1

if not exist "dist" mkdir "dist"

"%BUILD_ENV%\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "Co-pilot Facultate Legacy Client" ^
    --icon "%CLIENT_ICON%" ^
    --collect-all webview ^
    --hidden-import webview.platforms.edgechromium ^
    --hidden-import clr ^
    --distpath "dist" ^
    --workpath "build\client" ^
    --specpath "build\client" ^
    "%APP_ENTRY%"

if errorlevel 1 exit /b 1
echo Build complete: dist\Co-pilot Facultate Legacy Client.exe
if not defined CI pause
