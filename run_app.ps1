$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    & .\install.ps1
}

try {
    $response = Invoke-WebRequest -UseBasicParsing http://localhost:8501 -TimeoutSec 2
    if ($response.StatusCode -eq 200) {
        Start-Process "http://localhost:8501"
        return
    }
} catch {
}

& .\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false
