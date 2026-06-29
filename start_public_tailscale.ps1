$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StreamlitPort = 8501
$ApiPort = 8000

function Write-TrustedPeopleWarning {
    Write-Host ""
    Write-Host "ATENTIE: Funnel creeaza un URL PUBLIC pe Internet." -ForegroundColor Yellow
    Write-Host "Distribuie linkul numai persoanelor de incredere." -ForegroundColor Yellow
    Write-Host "Autentificarea ramane OFF: profilurile sunt fara parola si linkul trebuie pastrat privat." -ForegroundColor Yellow
}

function Write-ManualSteps {
    param([string]$Reason)

    Write-Host ""
    Write-Host ("Tailscale Funnel nu poate fi pornit automat: {0}" -f $Reason) -ForegroundColor Red
    Write-Host ""
    Write-Host "Pasi manuali exacti:" -ForegroundColor Cyan
    Write-Host "  1. Descarca Tailscale pentru Windows:"
    Write-Host "     https://tailscale.com/download/windows" -ForegroundColor Green
    Write-Host "  2. Instaleaza Tailscale, deschide aplicatia si autentifica-te."
    Write-Host "  3. Deschide PowerShell sau Command Prompt ca Administrator."
    Write-Host "  4. Verifica sesiunea:"
    Write-Host "     tailscale status" -ForegroundColor Green
    Write-Host "  5. Activeaza Funnel si aproba cererea din browser, daca apare:"
    Write-Host "     tailscale funnel --bg --https=443 --yes http://127.0.0.1:8501" -ForegroundColor Green
    Write-Host "  6. Verifica URL-ul public:"
    Write-Host "     tailscale funnel status --json" -ForegroundColor Green
    Write-Host "  7. Ruleaza din nou START_PUBLIC_TAILSCALE.bat."
    Write-Host ""
    Write-Host "Nu configura port forwarding in router." -ForegroundColor Yellow
    Write-TrustedPeopleWarning
}

function Find-TailscaleExecutable {
    $command = Get-Command "tailscale.exe" -ErrorAction SilentlyContinue
    $candidates = @()
    if ($command) {
        $candidates += $command.Source
    }
    $candidates += (Join-Path $env:ProgramFiles "Tailscale\tailscale.exe")
    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA "Tailscale\tailscale.exe")
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

function Invoke-Tailscale {
    param(
        [string]$Executable,
        [string[]]$Arguments
    )

    $output = & $Executable @Arguments 2>&1 | Out-String
    return [PSCustomObject]@{
        ExitCode = $LASTEXITCODE
        Output = $output.Trim()
    }
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

$tailscale = Find-TailscaleExecutable
if (-not $tailscale) {
    Write-ManualSteps "Tailscale nu este instalat sau tailscale.exe nu este in PATH."
    exit 10
}
Write-Host ("Tailscale detectat: {0}" -f $tailscale) -ForegroundColor Green

$statusResult = Invoke-Tailscale -Executable $tailscale -Arguments @("status", "--json")
if ($statusResult.ExitCode -ne 0 -or -not $statusResult.Output) {
    Write-ManualSteps "Nu pot citi starea Tailscale. Deschide aplicatia si autentifica-te."
    exit 11
}
try {
    $status = $statusResult.Output | ConvertFrom-Json
}
catch {
    Write-ManualSteps "Raspunsul Tailscale status nu este JSON valid."
    exit 12
}

$backendState = [string]$status.BackendState
$selfOnline = $false
if ($status.Self) {
    $selfOnline = [bool]$status.Self.Online
}
if ($backendState -ne "Running" -or -not $selfOnline) {
    Write-ManualSteps ("Tailscale nu este conectat (BackendState={0})." -f $backendState)
    exit 13
}
Write-Host "Tailscale este conectat." -ForegroundColor Green

$dnsName = [string]$status.Self.DNSName
$dnsName = $dnsName.Trim().TrimEnd(".")
if (-not $dnsName) {
    Write-ManualSteps "Dispozitivul nu are un nume MagicDNS; Funnel necesita MagicDNS si HTTPS."
    exit 14
}
$publicUrl = "https://$dnsName"

$funnelHelp = Invoke-Tailscale -Executable $tailscale -Arguments @("funnel", "--help")
if ($funnelHelp.ExitCode -ne 0 -or $funnelHelp.Output -match "unknown command|unknown subcommand") {
    Write-ManualSteps "Versiunea Tailscale instalata nu ofera comanda Funnel. Actualizeaza Tailscale."
    exit 15
}
Write-Host "Comanda Tailscale Funnel este disponibila." -ForegroundColor Green

$existingStreamlit = Test-HttpHealth "http://127.0.0.1:$StreamlitPort/_stcore/health"
if ($existingStreamlit) {
    try {
        $apiHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 3
        if ($apiHealth.authentication_enabled) {
            Write-ManualSteps "Serverul existent are autentificarea ON. Opreste-l si ruleaza din nou launcherul."
            exit 16
        }
        Write-Host "Serverul Faculty Copilot ruleaza deja cu autentificarea OFF." -ForegroundColor Green
    }
    catch {
        Write-ManualSteps "Portul Streamlit este ocupat, dar API-ul Faculty Copilot nu poate fi verificat."
        exit 17
    }
}

Write-TrustedPeopleWarning
Write-Host ""
Write-Host "Configurez Tailscale Funnel pe HTTPS 443..." -ForegroundColor Cyan
$funnelResult = Invoke-Tailscale -Executable $tailscale -Arguments @(
    "funnel",
    "--bg",
    "--https=443",
    "--yes",
    "http://127.0.0.1:$StreamlitPort"
)
if ($funnelResult.ExitCode -ne 0) {
    if ($funnelResult.Output) {
        Write-Host $funnelResult.Output -ForegroundColor Yellow
    }
    Write-ManualSteps "Tailscale a refuzat activarea Funnel."
    exit 18
}

if (-not $existingStreamlit) {
    $env:FACULTY_COPILOT_AUTH_ENABLED = "0"
    $env:FACULTY_COPILOT_DEFAULT_USER = "default_user"
    $env:FACULTY_COPILOT_DEPLOYMENT_MODE = "Public Internet"
    $env:FACULTY_COPILOT_PUBLIC_URL = $publicUrl
    $env:FACULTY_COPILOT_MAX_UPLOAD_MB = "100"
    $env:FACULTY_COPILOT_MAX_TOTAL_UPLOAD_MB = "250"
    $env:FACULTY_COPILOT_MAX_UPLOAD_FILES = "10"
    $env:FACULTY_COPILOT_IP_RATE_LIMIT = "60"
    $env:FACULTY_COPILOT_STREAMLIT_ACTION_RATE_LIMIT = "20"
    $env:FACULTY_COPILOT_MAX_CONCURRENT_UI_ACTIONS = "8"

    Write-Host "Pornesc Faculty Copilot pe desktop..." -ForegroundColor Cyan
    $startScript = Join-Path $ProjectRoot "start_server.bat"
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
        & $tailscale funnel --https=443 off | Out-Null
        Write-Host "Serverul Streamlit nu a pornit in 60 de secunde; Funnel a fost oprit." -ForegroundColor Red
        exit 19
    }
}

$funnelStatus = Invoke-Tailscale -Executable $tailscale -Arguments @("funnel", "status", "--json")
if ($funnelStatus.Output) {
    $urlMatch = [regex]::Match($funnelStatus.Output, "https://[A-Za-z0-9][A-Za-z0-9.-]*(?::[0-9]+)?")
    if ($urlMatch.Success) {
        $publicUrl = $urlMatch.Value.TrimEnd("/")
    }
}

Write-Host ""
Write-Host "====================================================" -ForegroundColor Green
Write-Host "FACULTY COPILOT ESTE PUBLIC" -ForegroundColor Green
Write-Host ("URL HTTPS: {0}" -f $publicUrl) -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Green
Write-TrustedPeopleWarning
Write-Host ""
Write-Host "Pentru oprirea accesului public:" -ForegroundColor Cyan
Write-Host "  tailscale funnel --https=443 off"
exit 0
