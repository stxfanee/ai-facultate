@echo off
setlocal
cd /d "%~dp0"

echo Build Faculty Copilot desktop client for Windows.
echo This client does NOT include Ollama, ChromaDB, AI models, or the server.
echo It opens the public/server web app inside a native WebView2 window.
echo.

if not exist "desktop_client\launcher.py" (
    echo Missing desktop_client\launcher.py.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_FOR_BUILD=.venv\Scripts\python.exe"
) else (
    set "PYTHON_FOR_BUILD=python"
)

if exist "desktop_client\.venv_build\Scripts\python.exe" (
    "desktop_client\.venv_build\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)"
    if errorlevel 1 (
        echo Recreating desktop client build environment for Python 3.11/3.12.
        rmdir /s /q "desktop_client\.venv_build"
    )
)

if not exist "desktop_client\.venv_build\Scripts\python.exe" (
    echo Creating PyInstaller build environment.
    "%PYTHON_FOR_BUILD%" -m venv desktop_client\.venv_build 2>nul
    if errorlevel 1 (
        echo Could not create build environment. Install Python 3.11 or 3.12.
        pause
        exit /b 1
    )
)

"desktop_client\.venv_build\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Could not update pip.
    pause
    exit /b 1
)

"desktop_client\.venv_build\Scripts\python.exe" -m pip install pyinstaller pywebview
if errorlevel 1 (
    echo Installing PyInstaller/pywebview failed.
    pause
    exit /b 1
)

if not exist "dist" mkdir "dist"
set "CLIENT_ICON=%CD%\desktop_client\assets\faculty_copilot.ico"
set "CLIENT_EXE=dist\Faculty Copilot.exe"

if exist "%CLIENT_EXE%" (
    del "%CLIENT_EXE%" >nul 2>nul
    if exist "%CLIENT_EXE%" (
        echo Close Faculty Copilot before rebuilding it.
        pause
        exit /b 1
    )
)

"desktop_client\.venv_build\Scripts\python.exe" -m PyInstaller ^
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
    "desktop_client\launcher.py"

if errorlevel 1 (
    echo Desktop client build failed.
    pause
    exit /b 1
)

echo.
echo Build complete:
echo dist\Faculty Copilot.exe

echo.
echo Optional installer:
echo If Inno Setup is installed, this script will also create dist\Faculty Copilot Setup.exe.
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if defined ISCC (
    "%ISCC%" "desktop_client\FacultyCopilot.iss"
    if errorlevel 1 (
        echo Inno Setup installer build failed, but the portable EXE was created.
    ) else (
        echo Installer complete: dist\Faculty Copilot Setup.exe
    )
) else (
    echo Inno Setup not found. Install it from https://jrsoftware.org/isinfo.php to build the optional installer.
)

echo.
pause

