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
    Write-Host "No .venv found, running setup..."
    & (Join-Path $ProjectRoot "scripts\setup.ps1")
}

# PyInstaller probes tkinter before application code can repair Tcl/Tk variables.
$PythonBase = (& $VenvPython -c "import sys; print(sys.base_prefix)").Trim()
$BundledTcl = Join-Path $PythonBase "tcl\tcl8.6"
$BundledTk = Join-Path $PythonBase "tcl\tk8.6"
if (Test-Path (Join-Path $BundledTcl "init.tcl")) {
    $env:TCL_LIBRARY = $BundledTcl
}
if (Test-Path (Join-Path $BundledTk "tk.tcl")) {
    $env:TK_LIBRARY = $BundledTk
}

Write-Host "Building with PyInstaller (onedir)..."
& $VenvPython -m PyInstaller HaiZaiQiDong.spec --noconfirm --clean

$OutDir = Join-Path $ProjectRoot "dist\HaiZaiQiDong"
if (Test-Path (Join-Path $OutDir "HaiZaiQiDong.exe")) {
    Write-Host ""
    Write-Host "Build complete:"
    Write-Host "  $OutDir\HaiZaiQiDong.exe"
    Write-Host ""
    Write-Host "Distribute the entire dist\HaiZaiQiDong folder."
} else {
    throw "Build failed: exe not found."
}
