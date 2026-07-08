@echo off
setlocal
cd /d "%~dp0"

echo Build Co-pilot Facultate unified desktop app for Windows.
echo This EXE can run in Server mode on the desktop PC or Client mode on another PC.
echo.

if not exist "desktop_app\launcher.py" (
    echo Missing desktop_app\launcher.py.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_FOR_BUILD=.venv\Scripts\python.exe"
) else (
    set "PYTHON_FOR_BUILD=python"
)

if exist "desktop_app\.venv_build\Scripts\python.exe" (
    "desktop_app\.venv_build\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)"
    if errorlevel 1 (
        echo Recreating unified app build environment for Python 3.11/3.12.
        rmdir /s /q "desktop_app\.venv_build"
    )
)

if not exist "desktop_app\.venv_build\Scripts\python.exe" (
    echo Creating PyInstaller build environment.
    "%PYTHON_FOR_BUILD%" -m venv desktop_app\.venv_build 2>nul
    if errorlevel 1 (
        echo Could not create build environment. Install Python 3.11 or 3.12.
        pause
        exit /b 1
    )
)

"desktop_app\.venv_build\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Could not update pip.
    pause
    exit /b 1
)

"desktop_app\.venv_build\Scripts\python.exe" -m pip install pyinstaller pywebview
if errorlevel 1 (
    echo Installing PyInstaller/pywebview failed.
    pause
    exit /b 1
)

if not exist "dist" mkdir "dist"
set "APP_ICON=%CD%\desktop_app\assets\copilot_facultate.ico"
set "APP_EXE=dist\Co-pilot Facultate.exe"

if exist "%APP_EXE%" (
    del "%APP_EXE%" >nul 2>nul
    if exist "%APP_EXE%" (
        echo Close Co-pilot Facultate before rebuilding it.
        pause
        exit /b 1
    )
)

"desktop_app\.venv_build\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "Co-pilot Facultate" ^
    --icon "%APP_ICON%" ^
    --add-data "%APP_ICON%;assets" ^
    --collect-all webview ^
    --hidden-import webview.platforms.edgechromium ^
    --hidden-import clr ^
    --distpath "dist" ^
    --workpath "build\desktop_app" ^
    --specpath "build\desktop_app" ^
    "desktop_app\launcher.py"

if errorlevel 1 (
    echo Unified app build failed.
    pause
    exit /b 1
)

echo.
echo Build complete:
echo dist\Co-pilot Facultate.exe
echo.
pause
