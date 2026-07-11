$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Exe,
        [string[]] $Arguments = @()
    )

    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Comanda a esuat: $Exe $($Arguments -join ' ')"
    }
}

function Test-SupportedPython {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Exe,
        [string[]] $Arguments = @()
    )

    try {
        & $Exe @Arguments -c "import sys; raise SystemExit(0 if sys.version_info[:2] in [(3, 11), (3, 12)] else 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

New-Item -ItemType Directory -Force -Path ".\documents" | Out-Null
New-Item -ItemType Directory -Force -Path ".\storage" | Out-Null

$pythonCommand = $null
$candidates = @()

if ($env:PYTHON_EXE) {
    $candidates += @{ Exe = $env:PYTHON_EXE; Args = @() }
}

$candidates += @(
    @{ Exe = "py"; Args = @("-3.12") },
    @{ Exe = "py"; Args = @("-3.11") },
    @{ Exe = "python"; Args = @() },
    @{ Exe = "python3"; Args = @() }
)

foreach ($candidate in $candidates) {
    if (Test-SupportedPython -Exe $candidate.Exe -Arguments $candidate.Args) {
        $pythonCommand = $candidate
        break
    }
}

if (-not $pythonCommand) {
    throw "Nu am gasit Python 3.11 sau 3.12. Instaleaza Python 3.12, apoi ruleaza din nou install.ps1."
}

Invoke-Checked -Exe $pythonCommand.Exe -Arguments (@($pythonCommand.Args) + @("-m", "venv", ".venv"))
Invoke-Checked -Exe ".\.venv\Scripts\python.exe" -Arguments @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked -Exe ".\.venv\Scripts\python.exe" -Arguments @("-m", "pip", "install", "-r", "requirements.txt")

Write-Host "Instalare finalizata in: $PSScriptRoot"
