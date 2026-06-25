@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    powershell -ExecutionPolicy Bypass -File "%~dp0install.ps1"
    if errorlevel 1 (
        echo Instalarea a esuat.
        pause
        exit /b 1
    )
)

set "AI_STUDY_SERVER_MODE=1"
set "AI_STUDY_SERVER_PORT=8501"

echo Pornesc AI Study Assistant in mod server.
echo Local: http://localhost:8501
echo Telefon/laptop in aceeasi retea: foloseste URL-ul LAN afisat in aplicatie.
echo Acces din afara casei: foloseste Tailscale, nu port forwarding.
echo.

".venv\Scripts\python.exe" -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true --browser.gatherUsageStats false

echo.
echo Serverul s-a oprit.
pause
