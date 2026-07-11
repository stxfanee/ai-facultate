$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    & .\install.ps1
}

New-Item -ItemType Directory -Force -Path ".\documents" | Out-Null
New-Item -ItemType Directory -Force -Path ".\storage" | Out-Null

$port = 8501
while ($port -le 8510) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $listener) {
        break
    }
    $port += 1
}

if ($port -gt 8510) {
    throw "Nu am gasit un port liber intre 8501 si 8510."
}

Write-Host "Pornesc AI Study Assistant din: $PSScriptRoot"
Write-Host "URL local: http://localhost:$port"

$env:AI_STUDY_SERVER_MODE = "0"
$env:AI_STUDY_SERVER_PORT = "$port"

& .\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port $port --server.headless false --browser.gatherUsageStats false
