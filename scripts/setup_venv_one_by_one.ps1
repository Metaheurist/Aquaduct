# Creates .venv in the project root, upgrades pip tooling, then runs
# scripts/install_pytorch.py --with-rest (PyTorch for your GPU/CPU + requirements.txt).
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
$InstallTorch = Join-Path $ProjectRoot "scripts\install_pytorch.py"
$ReqFile = Join-Path $ProjectRoot "requirements.txt"

if (-not (Test-Path $InstallTorch) -or -not (Test-Path $ReqFile)) {
    Write-Error "Missing scripts/install_pytorch.py or requirements.txt under: $ProjectRoot"
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

# 3) PyTorch (CUDA if NVIDIA GPU, else CPU; macOS: PyPI) + requirements.txt
Write-Host "=== [3] PyTorch + dependencies (scripts/install_pytorch.py --with-rest) ==="
& $VenvPython $InstallTorch --with-rest
if ($LASTEXITCODE -ne 0) {
    Write-Error "install_pytorch.py --with-rest failed"
    exit $LASTEXITCODE
}
Write-Host ""

Write-Host "=== Done. Activate with: .\.venv\Scripts\Activate.ps1 ==="
Write-Host "=== Then run: python -m UI   or   python UI/ui_app.py   or   python main.py --once ==="
