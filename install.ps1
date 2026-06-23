$ErrorActionPreference = "Stop"

$python = "python"
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    $bundledPython = "C:\Users\stefa\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $bundledPython) {
        $python = $bundledPython
    } else {
        throw "Python nu a fost gasit. Instaleaza Python 3.12 sau 3.11 si ruleaza din nou."
    }
}

& $python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Instalare finalizata."
