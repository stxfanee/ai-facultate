@echo off
setlocal
cd /d "%~dp0"

echo Build AI Study Copilot Client pentru Windows.
echo Clientul rezultat NU include Ollama, modele AI sau ChromaDB.
echo.

if not exist "client_app\main.py" (
    echo Lipseste client_app\main.py.
    pause
    exit /b 1
)

if not exist "client_app\.venv_build\Scripts\python.exe" (
    echo Creez mediul de build PyInstaller.
    py -3.12 -m venv client_app\.venv_build 2>nul
    if errorlevel 1 (
        py -3.11 -m venv client_app\.venv_build 2>nul
    )
    if not exist "client_app\.venv_build\Scripts\python.exe" (
        python -m venv client_app\.venv_build
    )
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

"client_app\.venv_build\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 (
    echo Instalarea PyInstaller a esuat.
    pause
    exit /b 1
)

if not exist "dist" mkdir "dist"

"client_app\.venv_build\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "AI Study Copilot Client" ^
    --distpath "dist" ^
    --workpath "build\client" ^
    --specpath "build\client" ^
    "client_app\main.py"

if errorlevel 1 (
    echo Build-ul a esuat.
    pause
    exit /b 1
)

echo.
echo Build finalizat:
echo dist\AI Study Copilot Client.exe
echo.
pause
