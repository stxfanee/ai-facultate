@echo off
setlocal
cd /d "%~dp0"

echo Building AI Study Copilot Server Launcher for Windows...
echo.

if not exist "server_launcher\launcher.py" (
    echo Missing server_launcher\launcher.py.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_FOR_BUILD=.venv\Scripts\python.exe"
) else (
    set "PYTHON_FOR_BUILD=python"
)

if not exist "server_launcher\.venv_build\Scripts\python.exe" (
    echo Creating isolated PyInstaller build environment...
    "%PYTHON_FOR_BUILD%" -m venv "server_launcher\.venv_build"
    if errorlevel 1 (
        echo Could not create the build environment. Install Python 3.11 or 3.12.
        pause
        exit /b 1
    )
)

"server_launcher\.venv_build\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :build_error
"server_launcher\.venv_build\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto :build_error

set "ICON_ARG="
if exist "client_app\assets\copilot_facultate.ico" (
    set "ICON_ARG=--icon %CD%\client_app\assets\copilot_facultate.ico"
)

if exist "dist\AI Study Copilot Server.exe" (
    del /q "dist\AI Study Copilot Server.exe" 2>nul
    if exist "dist\AI Study Copilot Server.exe" (
        echo Close AI Study Copilot Server before rebuilding it.
        pause
        exit /b 1
    )
)

"server_launcher\.venv_build\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "AI Study Copilot Server" ^
    %ICON_ARG% ^
    --distpath "dist" ^
    --workpath "build\server_launcher" ^
    --specpath "build\server_launcher" ^
    "server_launcher\launcher.py"

if errorlevel 1 goto :build_error

echo.
echo Build complete:
echo dist\AI Study Copilot Server.exe
echo.
pause
exit /b 0

:build_error
echo.
echo The launcher build failed. Check the messages above and your Internet connection.
pause
exit /b 1
