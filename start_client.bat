@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv_client\Scripts\python.exe" (
    echo Creez mediul Python minimal pentru client.
    py -3.12 -m venv .venv_client 2>nul
    if errorlevel 1 (
        py -3.11 -m venv .venv_client 2>nul
    )
    if not exist ".venv_client\Scripts\python.exe" (
        python -m venv .venv_client
    )
    if errorlevel 1 (
        echo Nu am putut crea mediul client. Instaleaza Python 3.11 sau 3.12.
        pause
        exit /b 1
    )
)

echo Instalez/actualizez dependintele clientului.
".venv_client\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Nu am putut actualiza pip.
    pause
    exit /b 1
)

".venv_client\Scripts\python.exe" -m pip install -r requirements-client.txt
if errorlevel 1 (
    echo Instalarea dependintelor clientului a esuat.
    pause
    exit /b 1
)

echo Pornesc Faculty Copilot Client.
echo Acest client nu ruleaza Ollama, nu descarca modele si nu creeaza ChromaDB.
echo.

".venv_client\Scripts\python.exe" -m streamlit run client.py --server.address 127.0.0.1 --server.port 8601 --server.headless false --browser.gatherUsageStats false

echo.
echo Clientul s-a oprit.
pause
