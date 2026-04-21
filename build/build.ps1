Param(
  [string]$Python = "python",
  [string]$VenvDir = ".venv-build",
  [switch]$Clean,
  [switch]$OneFile,
  [switch]$UI,
  # Use repo-root aquaduct-ui.spec (portable paths). Builds onefile windowless per spec; use for parity checks.
  [switch]$UseSpec
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

Write-Host "Installing PyTorch (CUDA if NVIDIA GPU, else CPU) + runtime dependencies"
python scripts/install_pytorch.py --with-rest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Installing build dependencies (pytest + PyInstaller, etc.)"
pip install -r requirements-dev.txt

if ($UseSpec) {
  if (-not $UI) { throw "-UseSpec requires -UI (desktop UI spec)." }
  Write-Host "Building via aquaduct-ui.spec (onefile windowless; see spec file)"
  $specPath = Join-Path $root "aquaduct-ui.spec"
  if (!(Test-Path $specPath)) { throw "Missing spec: $specPath" }
  pyinstaller $specPath --clean --noconfirm
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  $specExe = Join-Path $root "dist\aquaduct-ui.exe"
  if (Test-Path $specExe) {
    Write-Host "Running import smoke (AQUADUCT_IMPORT_SMOKE)"
    python (Join-Path $root "scripts\frozen_smoke.py") --exe $specExe
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
  Write-Host ""
  Write-Host "Build complete (spec)."
  Write-Host "Output: dist\\aquaduct-ui.exe"
  exit 0
}

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
  "--collect-all", "soundfile",
  # TTS + cloud APIs (explicit for --onefile static analysis)
  "--hidden-import", "pyttsx3",
  "--hidden-import", "requests",
  "--hidden-import", "charset_normalizer",
  "--hidden-import", "urllib3",
  "--hidden-import", "certifi",
  "--collect-all", "certifi",
  "--collect-all", "psutil",
  "--collect-all", "rich",
  "--collect-all", "bs4",
  "--collect-all", "lxml",
  "--collect-all", "dotenv",
  "--hidden-import", "src.speech.elevenlabs_tts",
  "--hidden-import", "src.content.characters_store"
)
if ($UI) {
  $extra += @(
    "--collect-submodules", "UI",
    "--hidden-import", "PyQt6.QtSvg",
    "--hidden-import", "main",
    "--hidden-import", "UI",
    "--hidden-import", "UI.ui_app",
    "--hidden-import", "UI.app",
    "--hidden-import", "UI.main_window",
    "--hidden-import", "UI.theme",
    "--hidden-import", "UI.workers",
    "--hidden-import", "UI.paths",
    "--hidden-import", "UI.no_wheel_controls",
    "--hidden-import", "UI.model_execution_toggle",
    "--hidden-import", "UI.api_model_widgets",
    "--hidden-import", "UI.tabs",
    "--hidden-import", "UI.tabs.characters_tab",
    "--hidden-import", "UI.tabs.api_tab",
    "--hidden-import", "UI.tabs.run_tab",
    "--hidden-import", "UI.tabs.settings_tab",
    "--hidden-import", "UI.tabs.video_tab",
    "--hidden-import", "UI.tabs.effects_tab",
    "--hidden-import", "UI.tabs.topics_tab",
    "--hidden-import", "UI.tabs.tasks_tab",
    "--hidden-import", "UI.tabs.branding_tab",
    "--hidden-import", "UI.tabs.captions_tab",
    "--hidden-import", "UI.tabs.my_pc_tab",
    "--hidden-import", "UI.tabs.library_tab",
    "--hidden-import", "UI.tabs.picture_tab",
    "--hidden-import", "UI.title_bar_outline_button",
    "--hidden-import", "UI.startup_splash",
    "--hidden-import", "UI.media_mode_toggle",
    "--hidden-import", "UI.library_fs",
    "--hidden-import", "UI.tab_sections",
    "--hidden-import", "UI.tutorial_dialog",
    "--hidden-import", "UI.tutorial_links",
    "--hidden-import", "src.util.cpu_parallelism",
    "--hidden-import", "src.runtime.pipeline_api",
    "--hidden-import", "src.runtime.generation_facade",
    # moviepy / imageio (often missed by static analysis)
    "--hidden-import", "imageio_ffmpeg",
    "--hidden-import", "imageio.plugins.ffmpeg",
    "--hidden-import", "imageio.plugins.pillow",
    # optional: main.py
    "--hidden-import", "dotenv"
  )
  # Bundle markdown docs (e.g. characters.md, elevenlabs.md) next to frozen tree
  $docsPath = Join-Path $root "docs"
  if (Test-Path $docsPath) {
    Get-ChildItem -Path $docsPath -Filter "*.md" -File -ErrorAction SilentlyContinue | ForEach-Object {
      $extra += @("--add-data", "$($_.FullName);docs")
    }
  }
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
  --copy-metadata "python-dotenv" `
  --copy-metadata "psutil" `
  --copy-metadata "rich" `
  --collect-all "moviepy" `
  --collect-all "imageio" `
  --collect-all "imageio_ffmpeg" `
  @uiQt `
  --hidden-import "PIL" `
  @extra `
  $entry

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($UI) {
  $uiExe = if ($OneFile) {
    Join-Path $root "dist\aquaduct-ui.exe"
  } else {
    Join-Path $root "dist\aquaduct-ui\aquaduct-ui.exe"
  }
  if (Test-Path $uiExe) {
    Write-Host "Running import smoke (AQUADUCT_IMPORT_SMOKE)"
    python (Join-Path $root "scripts\frozen_smoke.py") --exe $uiExe
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  } else {
    Write-Warning "Import smoke skipped: exe not found at $uiExe"
  }
}

Write-Host ""
Write-Host "Build complete."
Write-Host "Output folder: dist\\$name\\ (or dist\\$name.exe with --OneFile)"

