# BJAM Toolbox - Windows installer (PowerShell)
# Usage:  .\scripts\install.ps1   (from a local checkout)

$ErrorActionPreference = "Stop"
$MIN_PYTHON = [version]"3.9"
$PACKAGE = "bjam-toolbox"

function Info($msg)  { Write-Host "[info]  $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[ok]    $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[warn]  $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "[error] $msg" -ForegroundColor Red; exit 1 }

# ---------- detect Python ----------------------------------------------------
$python = $null
foreach ($cmd in @("python", "python3")) {
    try {
        $null = & $cmd --version 2>&1
        $python = $cmd
        break
    } catch { }
}
if (-not $python) {
    Fail "Python not found. Download it from https://www.python.org/downloads/ and check 'Add to PATH' during install."
}

$pyVersionRaw = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1
$pyVersion = [version]$pyVersionRaw
Info "Found $python ($pyVersion)"

if ($pyVersion -lt $MIN_PYTHON) {
    Fail "Python >= $MIN_PYTHON required (found $pyVersion)."
}

# ---------- check tkinter ----------------------------------------------------
$tkCheck = & $python -c "import tkinter" 2>&1
if ($LASTEXITCODE -ne 0) {
    Warn "tkinter not found."
    Warn "Re-run the Python installer and make sure 'tcl/tk and IDLE' is checked."
    Fail "tkinter is required but not installed."
}
Ok "tkinter is available"

# ---------- install ----------------------------------------------------------
Info "Installing $PACKAGE ..."

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
if (Test-Path "$projectRoot\pyproject.toml") {
    Info "Local checkout detected - installing from source."
    & $python -m pip install $projectRoot --quiet
} else {
    & $python -m pip install $PACKAGE --quiet
}

if ($LASTEXITCODE -ne 0) { Fail "pip install failed." }

# ---------- verify -----------------------------------------------------------
try {
    $version = & bjam-toolbox --version 2>&1
    Ok "Installation complete: $version"
} catch {
    Ok "Installation complete. If 'bjam-toolbox' is not on your PATH,"
    Ok "try: $python -m bjam_toolbox"
}

Info "Run 'bjam-toolbox' to launch the application."
