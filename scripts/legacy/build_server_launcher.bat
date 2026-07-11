@echo off
setlocal
cd /d "%~dp0\..\.."

echo Building legacy AI Study Copilot Server Launcher for Windows...
echo The flagship app is Co-pilot Facultate; this launcher remains for compatibility.
echo.

set "APP_DIR=apps\launcher"
set "BUILD_ENV=%APP_DIR%\.venv_build"
set "APP_ENTRY=%APP_DIR%\launcher.py"

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
"%BUILD_ENV%\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 exit /b 1

set "ICON_ARG="
if exist "assets\icons\copilot_facultate.ico" (
    set "ICON_ARG=--icon %CD%\assets\icons\copilot_facultate.ico"
)

if not exist "dist" mkdir "dist"
if exist "dist\AI Study Copilot Server.exe" del /q "dist\AI Study Copilot Server.exe" 2>nul

"%BUILD_ENV%\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "AI Study Copilot Server" ^
    %ICON_ARG% ^
    --distpath "dist" ^
    --workpath "build\server_launcher" ^
    --specpath "build\server_launcher" ^
    "%APP_ENTRY%"

if errorlevel 1 exit /b 1
echo Build complete: dist\AI Study Copilot Server.exe
if not defined CI pause
