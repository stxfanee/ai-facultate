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

rem Serverele accepta conexiuni de pe LAN/Tailscale, nu doar localhost.
set "FACULTY_COPILOT_API_HOST=0.0.0.0"
set "FACULTY_COPILOT_API_PORT=8000"
set "FACULTY_COPILOT_STREAMLIT_PORT=8501"
if "%FACULTY_COPILOT_START_STREAMLIT%"=="" set "FACULTY_COPILOT_START_STREAMLIT=1"
if "%FACULTY_COPILOT_AUTH_ENABLED%"=="" set "FACULTY_COPILOT_AUTH_ENABLED=0"
if "%FACULTY_COPILOT_DEFAULT_USER%"=="" set "FACULTY_COPILOT_DEFAULT_USER=default_user"
if "%FACULTY_COPILOT_DEPLOYMENT_MODE%"=="" if not "%FACULTY_COPILOT_PUBLIC_URL%"=="" set "FACULTY_COPILOT_DEPLOYMENT_MODE=Public Internet"
if "%FACULTY_COPILOT_DEPLOYMENT_MODE%"=="" set "FACULTY_COPILOT_DEPLOYMENT_MODE=LAN"
if "%FACULTY_COPILOT_MAX_UPLOAD_MB%"=="" set "FACULTY_COPILOT_MAX_UPLOAD_MB=100"
if "%FACULTY_COPILOT_MAX_TOTAL_UPLOAD_MB%"=="" set "FACULTY_COPILOT_MAX_TOTAL_UPLOAD_MB=250"
if "%FACULTY_COPILOT_MAX_UPLOAD_FILES%"=="" set "FACULTY_COPILOT_MAX_UPLOAD_FILES=10"
if "%FACULTY_COPILOT_IP_RATE_LIMIT%"=="" set "FACULTY_COPILOT_IP_RATE_LIMIT=60"
if "%FACULTY_COPILOT_MAX_CONCURRENT_REQUESTS%"=="" set "FACULTY_COPILOT_MAX_CONCURRENT_REQUESTS=32"
if "%FACULTY_COPILOT_API_TIMEOUT_SECONDS%"=="" set "FACULTY_COPILOT_API_TIMEOUT_SECONDS=600"
if "%FACULTY_COPILOT_STREAMLIT_ACTION_RATE_LIMIT%"=="" set "FACULTY_COPILOT_STREAMLIT_ACTION_RATE_LIMIT=20"
if "%FACULTY_COPILOT_MAX_CONCURRENT_UI_ACTIONS%"=="" set "FACULTY_COPILOT_MAX_CONCURRENT_UI_ACTIONS=8"
if "%FACULTY_COPILOT_TRUSTED_PROXY_IPS%"=="" set "FACULTY_COPILOT_TRUSTED_PROXY_IPS=127.0.0.1,::1"

set "FACULTY_COPILOT_SCHEME=http"
if not "%FACULTY_COPILOT_SSL_CERTFILE%"=="" if not "%FACULTY_COPILOT_SSL_KEYFILE%"=="" (
    set "FACULTY_COPILOT_SCHEME=https"
)

echo Pornesc Faculty Copilot API pe PC-ul server.
echo Ollama, ChromaDB si modelele ruleaza numai pe acest PC.
echo API local: %FACULTY_COPILOT_SCHEME%://localhost:%FACULTY_COPILOT_API_PORT%
echo API asculta pe: 0.0.0.0:%FACULTY_COPILOT_API_PORT%
echo Streamlit UI: http://localhost:%FACULTY_COPILOT_STREAMLIT_PORT%
echo Streamlit asculta pe: 0.0.0.0:%FACULTY_COPILOT_STREAMLIT_PORT%
echo Deployment mode: %FACULTY_COPILOT_DEPLOYMENT_MODE%
if not "%FACULTY_COPILOT_PUBLIC_URL%"=="" echo Public UI: %FACULTY_COPILOT_PUBLIC_URL%
if not "%FACULTY_COPILOT_PUBLIC_API_URL%"=="" echo Public API: %FACULTY_COPILOT_PUBLIC_API_URL%
echo Pentru HTTPS seteaza FACULTY_COPILOT_SSL_CERTFILE si FACULTY_COPILOT_SSL_KEYFILE.
echo Nu expune portul direct pe internet. Foloseste Tailscale pentru acces remote.
if "%FACULTY_COPILOT_AUTH_ENABLED%"=="1" (
    echo Autentificare: ON. Clientii trebuie sa foloseasca utilizator si parola/token.
) else (
    echo Autentificare: OFF. Toti clientii folosesc spatiul %FACULTY_COPILOT_DEFAULT_USER%.
)
echo Cont nou: .venv\Scripts\python.exe manage_users.py NUME --password "PAROLA"
echo Pentru multi-user seteaza FACULTY_COPILOT_AUTH_ENABLED=1 inainte de pornire.
echo Clientii remote isi incarca fisierele din propriul browser.
echo.

if "%FACULTY_COPILOT_START_STREAMLIT%"=="1" (
    echo Pornesc interfata Streamlit pentru clienti pe portul %FACULTY_COPILOT_STREAMLIT_PORT%.
    set "AI_STUDY_SERVER_MODE=1"
    set "AI_STUDY_SERVER_PORT=%FACULTY_COPILOT_STREAMLIT_PORT%"
    start "Copilot Facultate Streamlit" ".venv\Scripts\python.exe" -m streamlit run app.py --server.address 0.0.0.0 --server.port %FACULTY_COPILOT_STREAMLIT_PORT% --server.headless true --server.maxUploadSize %FACULTY_COPILOT_MAX_UPLOAD_MB% --server.enableXsrfProtection true --server.enableCORS true --server.enableWebsocketCompression true --browser.gatherUsageStats false
)

rem Diagnosticul ruleaza in fundal si asteapta pana cand FastAPI raspunde.
start "" /b powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0server_network_diagnostics.ps1" -ApiPort 8000 -StreamlitPort 8501

if "%FACULTY_COPILOT_SCHEME%"=="https" (
    ".venv\Scripts\python.exe" -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "%FACULTY_COPILOT_TRUSTED_PROXY_IPS%" --ssl-certfile "%FACULTY_COPILOT_SSL_CERTFILE%" --ssl-keyfile "%FACULTY_COPILOT_SSL_KEYFILE%"
) else (
    ".venv\Scripts\python.exe" -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "%FACULTY_COPILOT_TRUSTED_PROXY_IPS%"
)

echo.
echo Serverul API s-a oprit.
pause
