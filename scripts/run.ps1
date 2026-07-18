$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvReady = $false
if (Test-Path $VenvPython) {
    try {
        & $VenvPython -c "import sys" 2>$null
        $VenvReady = $LASTEXITCODE -eq 0
    } catch {
        $VenvReady = $false
    }
}

if (-not $VenvReady) {
    Write-Host "No working .venv found, running setup..."
    & (Join-Path $ProjectRoot "scripts\setup.ps1")
}

& $VenvPython main.py
