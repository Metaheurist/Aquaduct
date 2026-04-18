# Install PyTorch (and optionally all of requirements.txt) into BOTH:
#   - .venv (if present)
#   - a global Python install (default: Python 3.12 under Program Files)
#
# Usage (from repo root):
#   .\scripts\install_pytorch_venv_and_global.ps1
#   (default: streams to console and appends to logs/install-pytorch.log under the repo)
#   .\scripts\install_pytorch_venv_and_global.ps1 -NoLog
#   .\scripts\install_pytorch_venv_and_global.ps1 -LogFile logs\custom-install.log
#   .\scripts\install_pytorch_venv_and_global.ps1 -GlobalPython "C:\Program Files\Python311\python.exe"
#   .\scripts\install_pytorch_venv_and_global.ps1 -PyTorchOnly
#
# Requires: some `python` on PATH to run scripts\install_pytorch.py (only used to load the script; installs go to the --python targets).

param(
    [string]$GlobalPython = "C:\Program Files\Python312\python.exe",
    [switch]$PyTorchOnly,
    [string]$LogFile = "logs/install-pytorch.log",
    [switch]$NoLog
)

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo

if ($NoLog) {
    $LogFile = ""
}

if (-not (Test-Path "scripts\install_pytorch.py")) {
    Write-Error "scripts\install_pytorch.py not found. Run from the Aquaduct repo root."
}

$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
$targets = @()

if (Test-Path $venvPy) {
    $targets += $venvPy
    Write-Host "Will install into venv: $venvPy"
}
else {
    Write-Host "No .venv\Scripts\python.exe — skipping venv. Create one with: python -m venv .venv"
}

if (Test-Path $GlobalPython) {
    $targets += $GlobalPython
    Write-Host "Will install into global: $GlobalPython"
}
else {
    Write-Warning "Global Python not found at: $GlobalPython — pass -GlobalPython with a valid python.exe or install Python 3.12."
}

if ($targets.Count -eq 0) {
    Write-Error "Nothing to install: no .venv and no global Python. Fix paths or create a venv."
}

$installerArgs = @("scripts\install_pytorch.py")
if (-not $PyTorchOnly) {
    $installerArgs += "--with-rest"
}
foreach ($t in $targets) {
    $installerArgs += "--python"
    $installerArgs += $t
}

# -u = unbuffered stdout on the installer process; pip subprocesses already stream in Python.
$launcherArgs = @("-u") + $installerArgs

Write-Host ""
Write-Host "Running: python $($launcherArgs -join ' ')"

if ($LogFile) {
    $logPath = if ([System.IO.Path]::IsPathRooted($LogFile)) { $LogFile } else { Join-Path $repo $LogFile }
    $logDir = Split-Path -Parent $logPath
    if ($logDir -and -not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    Write-Host "Log file: $logPath"
    Write-Host ""
    & python @launcherArgs 2>&1 | Tee-Object -FilePath $logPath -Append
}
else {
    & python @launcherArgs
}

exit $LASTEXITCODE
