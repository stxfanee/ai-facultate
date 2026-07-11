$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$StreamlitPort = 8501
$ApiPort = 8000
$RuntimeDirectory = Join-Path $ProjectRoot "storage\runtime"
$PublicUrlFile = Join-Path $RuntimeDirectory "public_url.txt"
$CloudflaredOutputLog = Join-Path $RuntimeDirectory "cloudflared-output.log"
$CloudflaredErrorLog = Join-Path $RuntimeDirectory "cloudflared-error.log"

function Write-PublicWarning {
    Write-Host ""
    Write-Host "ATENTIE: linkul Cloudflare este PUBLIC pe Internet." -ForegroundColor Yellow
    Write-Host "Distribuie-l numai persoanelor de incredere." -ForegroundColor Yellow
    Write-Host "Autentificarea este OFF, iar profilurile fara parola nu sunt control de acces." -ForegroundColor Yellow
}

function Write-InstallInstructions {
    Write-Host "cloudflared nu este instalat sau nu a fost gasit." -ForegroundColor Red
    Write-Host ""
    Write-Host "Instalare recomandata pe Windows:" -ForegroundColor Cyan
    Write-Host "  winget install --id Cloudflare.cloudflared" -ForegroundColor Green
    Write-Host ""
    Write-Host "Alternativ, descarca executabilul oficial de la:" -ForegroundColor Cyan
    Write-Host "  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" -ForegroundColor Green
    Write-Host ""
    Write-Host "Dupa instalare, inchide si redeschide terminalul, apoi ruleaza din nou launcherul."
    Write-Host "Nu configura port forwarding in router." -ForegroundColor Yellow
}

function Find-CloudflaredExecutable {
    $command = Get-Command "cloudflared.exe" -ErrorAction SilentlyContinue
    $candidates = @()
    if ($command) {
        $candidates += $command.Source
    }
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles "cloudflared\cloudflared.exe")
        $candidates += (Join-Path $env:ProgramFiles "Cloudflare\Cloudflared\cloudflared.exe")
    }
    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\cloudflared.exe")
        $candidates += (Join-Path $env:LOCALAPPDATA "cloudflared\cloudflared.exe")
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

function Test-HttpHealth {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Read-LogFileShared {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    try {
        $stream = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite
        )
        try {
            $reader = New-Object System.IO.StreamReader($stream)
            try {
                return $reader.ReadToEnd()
            }
            finally {
                $reader.Dispose()
            }
        }
        finally {
            $stream.Dispose()
        }
    }
    catch {
        return ""
    }
}

$cloudflared = Find-CloudflaredExecutable
if (-not $cloudflared) {
    Write-InstallInstructions
    exit 10
}
Write-Host ("cloudflared detectat: {0}" -f $cloudflared) -ForegroundColor Green

New-Item -ItemType Directory -Path $RuntimeDirectory -Force | Out-Null
Remove-Item -LiteralPath $PublicUrlFile -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $CloudflaredOutputLog -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $CloudflaredErrorLog -Force -ErrorAction SilentlyContinue

$streamlitWasRunning = Test-HttpHealth "http://127.0.0.1:$StreamlitPort/_stcore/health"
if ($streamlitWasRunning) {
    try {
        $apiHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 3
        if ($apiHealth.authentication_enabled) {
            Write-Host "Serverul existent are autentificarea ON; launcherul nu o va modifica." -ForegroundColor Yellow
        }
        else {
            Write-Host "Serverul ruleaza deja cu autentificarea OFF." -ForegroundColor Green
        }
    }
    catch {
        Write-Host "Streamlit ruleaza deja; API-ul de pe 8000 nu a putut fi verificat." -ForegroundColor Yellow
    }
}

Write-PublicWarning
Write-Host ""
Write-Host "Creez un Cloudflare Quick Tunnel catre Streamlit 8501..." -ForegroundColor Cyan
$tunnelProcess = Start-Process -FilePath $cloudflared `
    -ArgumentList @("tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$StreamlitPort") `
    -RedirectStandardOutput $CloudflaredOutputLog `
    -RedirectStandardError $CloudflaredErrorLog `
    -WindowStyle Hidden `
    -PassThru

$publicUrl = $null
for ($attempt = 1; $attempt -le 45; $attempt++) {
    Start-Sleep -Seconds 1
    if ($tunnelProcess.HasExited) {
        break
    }
    foreach ($logFile in @($CloudflaredOutputLog, $CloudflaredErrorLog)) {
        $logText = Read-LogFileShared $logFile
        $match = [regex]::Match([string]$logText, "https://[a-z0-9-]+\.trycloudflare\.com")
        if ($match.Success) {
            $publicUrl = $match.Value.TrimEnd("/")
            break
        }
    }
    if ($publicUrl) { break }
}

if (-not $publicUrl) {
    if (-not $tunnelProcess.HasExited) {
        Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Cloudflare nu a furnizat un URL in 45 de secunde." -ForegroundColor Red
    if (Test-Path -LiteralPath $CloudflaredErrorLog) {
        Get-Content -LiteralPath $CloudflaredErrorLog -Tail 20
    }
    Write-Host "Verifica accesul outbound la Internet si ruleaza din nou launcherul."
    exit 11
}

Set-Content -LiteralPath $PublicUrlFile -Value $publicUrl -Encoding UTF8
$env:FACULTY_COPILOT_AUTH_ENABLED = "0"
$env:FACULTY_COPILOT_DEFAULT_USER = "default_user"
$env:FACULTY_COPILOT_DEPLOYMENT_MODE = "Public Internet"
$env:FACULTY_COPILOT_PUBLIC_URL = $publicUrl
$env:FACULTY_COPILOT_MAX_UPLOAD_MB = "100"
$env:FACULTY_COPILOT_MAX_TOTAL_UPLOAD_MB = "250"
$env:FACULTY_COPILOT_MAX_UPLOAD_FILES = "10"
$env:FACULTY_COPILOT_IP_RATE_LIMIT = "60"
$env:FACULTY_COPILOT_MAX_CONCURRENT_REQUESTS = "32"
$env:FACULTY_COPILOT_API_TIMEOUT_SECONDS = "600"
$env:FACULTY_COPILOT_STREAMLIT_ACTION_RATE_LIMIT = "20"
$env:FACULTY_COPILOT_MAX_CONCURRENT_UI_ACTIONS = "8"

if (-not $streamlitWasRunning) {
    Write-Host "Pornesc Co-pilot Facultate pe desktop..." -ForegroundColor Cyan
    $startScript = Join-Path $ProjectRoot "scripts\start\start_local_server.bat"
    Start-Process -FilePath $env:ComSpec `
        -ArgumentList ("/c `"{0}`"" -f $startScript) `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Minimized | Out-Null

    $serverReady = $false
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        if (Test-HttpHealth "http://127.0.0.1:$StreamlitPort/_stcore/health") {
            $serverReady = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $serverReady) {
        Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $PublicUrlFile -Force -ErrorAction SilentlyContinue
        Write-Host "Streamlit nu a pornit in 60 de secunde; tunnel-ul a fost oprit." -ForegroundColor Red
        exit 12
    }
}

Write-Host ""
Write-Host "====================================================" -ForegroundColor Green
Write-Host "AI STUDY COPILOT ESTE PUBLIC" -ForegroundColor Green
Write-Host ("URL HTTPS: {0}" -f $publicUrl) -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Green
Write-Host "Streamlit public: DA (port local 8501)"
Write-Host "FastAPI public: NU (ramane local pe portul 8000)"
Write-PublicWarning
Write-Host ""
Write-Host "Pastreaza aceasta fereastra deschisa. Ctrl+C sau inchiderea ei opreste tunnel-ul." -ForegroundColor Cyan

try {
    Wait-Process -Id $tunnelProcess.Id
}
finally {
    Remove-Item -LiteralPath $PublicUrlFile -Force -ErrorAction SilentlyContinue
}
exit 0
