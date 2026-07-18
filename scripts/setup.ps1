$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$PythonCandidates = @()
if ($env:MOUSE_SKETCH_PYTHON) {
    $PythonCandidates += @{ Command = $env:MOUSE_SKETCH_PYTHON; Args = @() }
}
$PythonCandidates += @(
    @{ Command = (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"); Args = @() },
    @{ Command = (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"); Args = @() },
    @{ Command = "py"; Args = @("-3.12") },
    @{ Command = "py"; Args = @("-3.11") },
    @{ Command = "py"; Args = @("-3.10") },
    @{ Command = "py"; Args = @("-3.9") },
    @{ Command = "python"; Args = @() }
)

$PythonCmd = $null
$PythonArgs = @()
foreach ($candidate in $PythonCandidates) {
    try {
        & $candidate.Command @($candidate.Args) -c "import sys; assert (3, 9) <= sys.version_info[:2] <= (3, 12)" 2>$null
        if ($LASTEXITCODE -ne 0) { continue }
        $PythonCmd = $candidate.Command
        $PythonArgs = $candidate.Args
        break
    } catch {
        continue
    }
}

if (-not $PythonCmd) {
    throw "Python 3.9-3.12 not found. Install Python 3.12 and run this script again."
}

Write-Host "Using interpreter: $PythonCmd $PythonArgs"

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $VenvValid = $false
    try {
        & $VenvPython -c "import sys" 2>$null
        $VenvValid = $LASTEXITCODE -eq 0
    } catch {
        $VenvValid = $false
    }
    if (-not $VenvValid) {
        Write-Host "Removing invalid virtual environment..."
        Remove-Item -LiteralPath (Join-Path $ProjectRoot ".venv") -Recurse -Force
    }
}

if (-not (Test-Path $VenvPython)) {
    & $PythonCmd @PythonArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment." }
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }
& $VenvPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Failed to install dependencies." }

Write-Host ""
Write-Host "Environment ready."
Write-Host "Run:    .\.venv\Scripts\python.exe main.py"
Write-Host "Build:  .\scripts\build.ps1"
