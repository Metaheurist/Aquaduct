# Dot-source from repo root so your shell uses .venv:
#   cd C:\Users\OnceU\OneDrive\Documents\GitHub\Aquaduct
#   . .\scripts\setup_terminal_env.ps1
#
# If activation is blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$activate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $activate) {
    . $activate
    Write-Host "Activated: $RepoRoot\.venv" -ForegroundColor Green
} else {
    Write-Host "No .venv yet. Create and install:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv" -ForegroundColor Gray
    Write-Host "  .\.venv\Scripts\python.exe scripts\install_pytorch.py --with-rest" -ForegroundColor Gray
}

# Optional: Hugging Face (same names the app uses; set your token here or in the UI)
if (-not $env:HF_TOKEN -and -not $env:HUGGINGFACEHUB_API_TOKEN) {
    Write-Host "Tip: set HF_TOKEN=hf_... for gated Hub models (or use Settings -> API)." -ForegroundColor DarkGray
}
