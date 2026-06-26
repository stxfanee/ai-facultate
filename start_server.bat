@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    powershell -ExecutionPolicy Bypass -File "%~dp0install.ps1"
    if errorlevel 1 (
        echo Instalarea serverului a esuat.
        pause
        exit /b 1
    )
)

if "%FACULTY_COPILOT_API_HOST%"=="" set "FACULTY_COPILOT_API_HOST=0.0.0.0"
if "%FACULTY_COPILOT_API_PORT%"=="" set "FACULTY_COPILOT_API_PORT=8000"
if "%FACULTY_COPILOT_STREAMLIT_PORT%"=="" set "FACULTY_COPILOT_STREAMLIT_PORT=8501"
if "%FACULTY_COPILOT_START_STREAMLIT%"=="" set "FACULTY_COPILOT_START_STREAMLIT=1"

set "FACULTY_COPILOT_SCHEME=http"
if not "%FACULTY_COPILOT_SSL_CERTFILE%"=="" if not "%FACULTY_COPILOT_SSL_KEYFILE%"=="" (
    set "FACULTY_COPILOT_SCHEME=https"
)

echo Pornesc Faculty Copilot API pe PC-ul server.
echo Ollama, ChromaDB si modelele ruleaza numai pe acest PC.
echo API local: %FACULTY_COPILOT_SCHEME%://localhost:%FACULTY_COPILOT_API_PORT%
echo API LAN/Tailscale: foloseste adresa acestui PC + portul %FACULTY_COPILOT_API_PORT%.
echo Streamlit UI: http://localhost:%FACULTY_COPILOT_STREAMLIT_PORT%
echo Pentru HTTPS seteaza FACULTY_COPILOT_SSL_CERTFILE si FACULTY_COPILOT_SSL_KEYFILE.
echo Nu expune portul direct pe internet. Foloseste Tailscale pentru acces remote.
echo.

if "%FACULTY_COPILOT_START_STREAMLIT%"=="1" (
    echo Pornesc interfata Streamlit pentru clienti pe portul %FACULTY_COPILOT_STREAMLIT_PORT%.
    set "AI_STUDY_SERVER_MODE=1"
    set "AI_STUDY_SERVER_PORT=%FACULTY_COPILOT_STREAMLIT_PORT%"
    start "Copilot Facultate Streamlit" ".venv\Scripts\python.exe" -m streamlit run app.py --server.address 0.0.0.0 --server.port %FACULTY_COPILOT_STREAMLIT_PORT% --server.headless true --browser.gatherUsageStats false
)

if "%FACULTY_COPILOT_SCHEME%"=="https" (
    ".venv\Scripts\python.exe" -m uvicorn api_server:app --host %FACULTY_COPILOT_API_HOST% --port %FACULTY_COPILOT_API_PORT% --ssl-certfile "%FACULTY_COPILOT_SSL_CERTFILE%" --ssl-keyfile "%FACULTY_COPILOT_SSL_KEYFILE%"
) else (
    ".venv\Scripts\python.exe" -m uvicorn api_server:app --host %FACULTY_COPILOT_API_HOST% --port %FACULTY_COPILOT_API_PORT%
)

echo.
echo Serverul API s-a oprit.
pause
