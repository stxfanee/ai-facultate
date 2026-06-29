param(
    [int]$ApiPort = 8000,
    [int]$StreamlitPort = 8501
)

$ErrorActionPreference = "SilentlyContinue"
$addresses = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -ne "127.0.0.1" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.AddressState -eq "Preferred"
    } |
    Select-Object -ExpandProperty IPAddress -Unique

Write-Host ""
Write-Host "================ DIAGNOSTIC RETEA ================" -ForegroundColor Cyan
if (-not $addresses) {
    Write-Host "Nu am gasit nicio adresa IPv4 LAN/Tailscale activa." -ForegroundColor Yellow
}
else {
    Write-Host "Adrese IP locale:"
    foreach ($address in $addresses) {
        Write-Host ("  - {0}" -f $address)
    }

    Write-Host ""
    Write-Host "Adrese disponibile pentru laptop:"
    foreach ($address in $addresses) {
        Write-Host ("  FastAPI:   http://{0}:{1}" -f $address, $ApiPort) -ForegroundColor Green
        Write-Host ("  Health:    http://{0}:{1}/health" -f $address, $ApiPort) -ForegroundColor Green
        Write-Host ("  Streamlit: http://{0}:{1}" -f $address, $StreamlitPort) -ForegroundColor Green
    }
}

$healthUrl = "http://127.0.0.1:$ApiPort/health"
$healthResult = $null
for ($attempt = 1; $attempt -le 20; $attempt++) {
    try {
        $healthResult = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
        break
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

Write-Host ""
if ($healthResult -and $healthResult.api) {
    Write-Host ("Health check: OK ({0})" -f $healthUrl) -ForegroundColor Green
    $ollamaStatus = if ($healthResult.ollama) { "pornit" } else { "oprit/indisponibil" }
    Write-Host ("Ollama: {0}" -f $ollamaStatus)
}
else {
    Write-Host ("Health check: EROARE ({0})" -f $healthUrl) -ForegroundColor Red
    Write-Host "FastAPI nu a raspuns in 20 de secunde. Verifica mesajele uvicorn de mai sus." -ForegroundColor Yellow
}

$apiListening = Get-NetTCPConnection -State Listen -LocalPort $ApiPort
$streamlitListening = Get-NetTCPConnection -State Listen -LocalPort $StreamlitPort
$apiState = if ($apiListening) { "LISTENING" } else { "NU ASCULTA" }
$streamlitState = if ($streamlitListening) { "LISTENING" } else { "NU ASCULTA" }
Write-Host ("Port {0}: {1}" -f $ApiPort, $apiState)
Write-Host ("Port {0}: {1}" -f $StreamlitPort, $streamlitState)
Write-Host "===================================================="
Write-Host ""
