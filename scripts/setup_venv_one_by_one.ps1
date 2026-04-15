# Creates .venv in the project root, upgrades pip tooling first, then installs
# each line of requirements.txt one package at a time (easier to see progress / failures).
#
# Usage (from repo root):
#   .\scripts\setup_venv_one_by_one.ps1
#
# Or:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_venv_one_by_one.ps1

$ErrorActionPreference = "Stop"

# Script lives in scripts/ — repo root is one level up
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Set-Location $ProjectRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ReqFile = Join-Path $ProjectRoot "requirements.txt"

if (-not (Test-Path $ReqFile)) {
    Write-Error "requirements.txt not found at: $ReqFile"
    exit 1
}

Write-Host "Project root: $ProjectRoot"
Write-Host ""

# 1) Create venv
if (-not (Test-Path $VenvPython)) {
    Write-Host "=== [1] Creating virtual environment (.venv) ==="
    & python -m venv (Join-Path $ProjectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "=== [1] .venv already exists, skipping create ==="
}

Write-Host ""

# 2) Upgrade pip, setuptools, wheel first
Write-Host "=== [2] Upgrading pip, setuptools, wheel ==="
& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""

# 3) Enumerate and install each requirement line
$lines = Get-Content $ReqFile -Encoding UTF8 | ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and ($_ -notmatch '^\s*#') }

$index = 0
$total = @($lines).Count
Write-Host "=== [3] Installing $total packages from requirements.txt (one by one) ==="
Write-Host ""

foreach ($req in $lines) {
    $index++
    Write-Host "------------------------------------------------------------"
    Write-Host "[$index / $total] Installing: $req"
    Write-Host "------------------------------------------------------------"
    & $VenvPython -m pip install $req
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pip install failed for: $req"
        exit $LASTEXITCODE
    }
    Write-Host ""
}

Write-Host "=== Done. Activate with: .\.venv\Scripts\Activate.ps1 ==="
Write-Host "=== Then run: python -m UI   or   python UI/ui_app.py   or   python main.py --once ==="
