@echo off
setlocal
cd /d "%~dp0"

echo Build Copilot Facultate launcher pentru Windows.
echo Launcherul rezultat NU include Ollama, modele AI sau ChromaDB.
echo El deschide interfata Streamlit a serverului intr-o fereastra WebView2.
echo.

if not exist "client_app\launcher.py" (
    echo Lipseste client_app\launcher.py.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_FOR_BUILD=.venv\Scripts\python.exe"
) else (
    set "PYTHON_FOR_BUILD=python"
)

if exist "client_app\.venv_build\Scripts\python.exe" (
    "client_app\.venv_build\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)"
    if errorlevel 1 (
        echo Refac mediul de build pentru Python 3.11/3.12.
        rmdir /s /q "client_app\.venv_build"
    )
)

if not exist "client_app\.venv_build\Scripts\python.exe" (
    echo Creez mediul de build PyInstaller.
    "%PYTHON_FOR_BUILD%" -m venv client_app\.venv_build 2>nul
    if errorlevel 1 (
        echo Nu am putut crea mediul de build. Instaleaza Python 3.11 sau 3.12.
        pause
        exit /b 1
    )
)

"client_app\.venv_build\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Nu am putut actualiza pip.
    pause
    exit /b 1
)

"client_app\.venv_build\Scripts\python.exe" -m pip install pyinstaller pywebview
if errorlevel 1 (
    echo Instalarea PyInstaller/pywebview a esuat.
    pause
    exit /b 1
)

if not exist "dist" mkdir "dist"
set "CLIENT_ICON=%CD%\client_app\assets\copilot_facultate.ico"

"client_app\.venv_build\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "Copilot Facultate" ^
    --icon "%CLIENT_ICON%" ^
    --collect-all webview ^
    --hidden-import webview.platforms.edgechromium ^
    --hidden-import clr ^
    --distpath "dist" ^
    --workpath "build\client" ^
    --specpath "build\client" ^
    "client_app\launcher.py"

if errorlevel 1 (
    echo Build-ul a esuat.
    pause
    exit /b 1
)

echo.
echo Build finalizat:
echo dist\Copilot Facultate.exe
echo.
pause
