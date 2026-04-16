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

Write-Host "== Aquaduct: Windows EXE build =="
Assert-Command $Python

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if ($Clean) {
  if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
  if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
  # IMPORTANT: do NOT delete the repo's build/ folder (this script lives there).
  if (Test-Path "build\\aquaduct") { Remove-Item -Recurse -Force "build\\aquaduct" }
  if (Test-Path "build\\aquaduct-ui") { Remove-Item -Recurse -Force "build\\aquaduct-ui" }
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
$name = "aquaduct"
if ($UI) {
  $entry = "UI\\ui_app.py"
  $name = "aquaduct-ui"
}

# Note: models + ffmpeg are downloaded at runtime into .cache/
# Bundle the full app tree + repo files the UI reads (e.g. requirements.txt next to the frozen tree).
$extra = @(
  "--collect-submodules", "src",
  "--collect-submodules", "debug",
  "--add-data", "requirements.txt;.",
  "--hidden-import", "soundfile",
  "--collect-all", "soundfile"
)
if ($UI) {
  $extra += @(
    "--collect-submodules", "UI",
    "--hidden-import", "main",
    "--hidden-import", "UI",
    "--hidden-import", "UI.ui_app",
    "--hidden-import", "UI.app",
    "--hidden-import", "UI.main_window",
    "--hidden-import", "UI.theme",
    "--hidden-import", "UI.workers",
    "--hidden-import", "UI.paths",
    "--hidden-import", "UI.tabs",
    # moviepy / imageio (often missed by static analysis)
    "--hidden-import", "imageio_ffmpeg",
    "--hidden-import", "imageio.plugins.ffmpeg",
    "--hidden-import", "imageio.plugins.pillow",
    # optional: main.py
    "--hidden-import", "dotenv"
  )
}

$uiQt = @()
if ($UI) {
  $uiQt = @("--collect-all", "PyQt6")
}

# UI builds: no console window (use `aquaduct-ui.exe -debug` for a console; see UI/ui_app.py).
$uiWindowed = @()
if ($UI) {
  $uiWindowed = @("--noconsole")
}

pyinstaller $mode `
  --name $name `
  --clean `
  --noconfirm `
  @uiWindowed `
  --copy-metadata "imageio" `
  --copy-metadata "imageio-ffmpeg" `
  --copy-metadata "moviepy" `
  --copy-metadata "proglog" `
  --copy-metadata "decorator" `
  --copy-metadata "tqdm" `
  --copy-metadata "torch" `
  --copy-metadata "transformers" `
  --copy-metadata "diffusers" `
  --copy-metadata "huggingface_hub" `
  --copy-metadata "accelerate" `
  --copy-metadata "safetensors" `
  --copy-metadata "bitsandbytes" `
  --collect-all "moviepy" `
  --collect-all "imageio" `
  --collect-all "imageio_ffmpeg" `
  @uiQt `
  --hidden-import "PIL" `
  @extra `
  $entry

Write-Host ""
Write-Host "Build complete."
Write-Host "Output folder: dist\\$name\\ (or dist\\$name.exe with --OneFile)"

