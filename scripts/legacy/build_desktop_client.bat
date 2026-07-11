@echo off
setlocal
cd /d "%~dp0\..\.."

echo Build legacy Faculty Copilot desktop client for Windows.
echo The flagship app is Co-pilot Facultate; this legacy client remains for compatibility.
echo.

set "APP_DIR=apps\client"
set "BUILD_ENV=%APP_DIR%\.venv_build"
set "APP_ENTRY=%APP_DIR%\launcher.py"
set "CLIENT_ICON=%CD%\%APP_DIR%\assets\faculty_copilot.ico"
set "CLIENT_EXE=dist\Faculty Copilot.exe"

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
    echo Creating PyInstaller build environment.
    "%PYTHON_FOR_BUILD%" -m venv "%BUILD_ENV%"
    if errorlevel 1 (
        echo Could not create build environment.
        if not defined CI pause
        exit /b 1
    )
)

"%BUILD_ENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%BUILD_ENV%\Scripts\python.exe" -m pip install pyinstaller pywebview
if errorlevel 1 exit /b 1

if not exist "dist" mkdir "dist"
if exist "%CLIENT_EXE%" del "%CLIENT_EXE%" >nul 2>nul

"%BUILD_ENV%\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "Faculty Copilot" ^
    --icon "%CLIENT_ICON%" ^
    --add-data "%CLIENT_ICON%;assets" ^
    --collect-all webview ^
    --hidden-import webview.platforms.edgechromium ^
    --hidden-import clr ^
    --distpath "dist" ^
    --workpath "build\desktop_client" ^
    --specpath "build\desktop_client" ^
    "%APP_ENTRY%"

if errorlevel 1 (
    echo Desktop client build failed.
    if not defined CI pause
    exit /b 1
)

echo Build complete: %CLIENT_EXE%
if not defined CI pause
