Param(
  [string]$Python = "python",
  [string]$VenvDir = ".venv-build",
  [switch]$Clean,
  [switch]$OneFile,
  [switch]$UI
)

$ErrorActionPreference = "Stop"

function Assert-Command($cmd) {
  $null = Get-Command $cmd -ErrorAction Stop
}

function Activate-Venv([string]$venvPath) {
  $activate = Join-Path $venvPath "Scripts\\Activate.ps1"
  if (!(Test-Path $activate)) { throw "Missing venv activate script: $activate" }
  . $activate
}

Write-Host "== Local AI News Factory: Windows EXE build =="
Assert-Command $Python

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if ($Clean) {
  if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
  if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
  # IMPORTANT: do NOT delete the repo's build/ folder (this script lives there).
  if (Test-Path "build\\ai-news-factory") { Remove-Item -Recurse -Force "build\\ai-news-factory" }
  if (Test-Path "build\\ai-news-factory-ui") { Remove-Item -Recurse -Force "build\\ai-news-factory-ui" }
}

Write-Host "Creating build venv at $VenvDir"
& $Python -m venv $VenvDir
Activate-Venv $VenvDir

Write-Host "Upgrading pip"
python -m pip install --upgrade pip

Write-Host "Installing runtime dependencies"
pip install -r requirements.txt

Write-Host "Installing build dependencies"
pip install -r build\\requirements-build.txt

Write-Host "Building exe with PyInstaller"
$mode = "--onedir"
if ($OneFile) { $mode = "--onefile" }

# Build entrypoint selection
$entry = "main.py"
$name = "ai-news-factory"
if ($UI) {
  $entry = "UI\\ui_app.py"
  $name = "ai-news-factory-ui"
}

# Note: models + ffmpeg are downloaded at runtime into .cache/
$extra = @()
if ($UI) {
  $extra += @(
    "--hidden-import", "UI",
    "--hidden-import", "UI.ui_app",
    "--hidden-import", "UI.app",
    "--hidden-import", "UI.main_window",
    "--hidden-import", "UI.theme",
    "--hidden-import", "UI.workers",
    "--hidden-import", "UI.paths",
    "--hidden-import", "UI.tabs"
  )
}

pyinstaller $mode `
  --name $name `
  --clean `
  --noconfirm `
  --collect-all "moviepy" `
  --collect-all "imageio_ffmpeg" `
  --collect-all "PyQt6" `
  --hidden-import "PIL" `
  @extra `
  $entry

Write-Host ""
Write-Host "Build complete."
Write-Host "Output folder: dist\\$name\\ (or dist\\$name.exe with --OneFile)"

