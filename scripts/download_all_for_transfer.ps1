# Autonomous: no parameters, no prompts. Double-click or:
#   powershell -ExecutionPolicy Bypass -File .\scripts\download_all_for_transfer.ps1
#
# Creates/uses repo .venv, runs PyTorch + requirements, downloads full curated HF set.
# HF_TOKEN: set in repo .env (or environment) for gated models.
# If this file is not under <repo>\scripts\, edit $DefaultAquaductRepo below once.

$ErrorActionPreference = "Stop"

$ScriptRoot = $PSScriptRoot
$DefaultAquaductRepo = "C:\Users\OnceU\OneDrive\Documents\GitHub\Aquaduct"

$parent = Split-Path -Parent $ScriptRoot
if (Test-Path -LiteralPath (Join-Path $parent "src\torch_install.py")) {
    $RepoRoot = $parent
}
elseif (Test-Path -LiteralPath (Join-Path $ScriptRoot "src\torch_install.py")) {
    $RepoRoot = $ScriptRoot
}
elseif (Test-Path -LiteralPath (Join-Path $DefaultAquaductRepo "src\torch_install.py")) {
    $RepoRoot = $DefaultAquaductRepo
}
else {
    Write-Error "Could not find Aquaduct (src\torch_install.py). Edit `$DefaultAquaductRepo in this script to your clone path."
}

$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
Set-Location $RepoRoot

if ((Split-Path -Leaf $ScriptRoot) -eq "scripts") {
    $ModelsOut = Join-Path $RepoRoot "models"
}
else {
    $ModelsOut = Join-Path $ScriptRoot "models"
}
$ModelsOut = [System.IO.Path]::GetFullPath($ModelsOut)

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $k = $line.Substring(0, $eq).Trim()
        $v = $line.Substring($eq + 1).Trim()
        if ($v.Length -ge 2 -and $v.StartsWith([char]0x22) -and $v.EndsWith([char]0x22)) {
            $v = $v.Substring(1, $v.Length - 2)
        }
        Set-Item -Path "Env:$k" -Value $v
    }
}

Import-DotEnv (Join-Path $RepoRoot ".env")

$ReqFile = Join-Path $RepoRoot "requirements.txt"
$TorchInstallSrc = Join-Path $RepoRoot "src\torch_install.py"
if (-not (Test-Path -LiteralPath $ReqFile) -or -not (Test-Path -LiteralPath $TorchInstallSrc)) {
    Write-Error "Not an Aquaduct repo (missing requirements.txt or src\torch_install.py): $RepoRoot"
}

$LogsDir = Join-Path $ScriptRoot "logs"
if (-not (Test-Path -LiteralPath $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}
$TranscriptPath = Join-Path $LogsDir ("download-all-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

$TempDir = Join-Path $env:TEMP ("aquaduct_dl_{0}" -f [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
$PyTorchBootstrap = Join-Path $TempDir "install_torch_embed.py"
$PyHfDownload = Join-Path $TempDir "download_hf_embed.py"

@'
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    root = os.environ.get("AQUADUCT_ROOT")
    if not root:
        print("AQUADUCT_ROOT is not set", file=sys.stderr)
        return 1
    root_p = Path(root).resolve()
    p = str(root_p)
    if p not in sys.path:
        sys.path.insert(0, p)
    from src.torch_install import main as run

    return int(run())


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $PyTorchBootstrap -Encoding UTF8

@'
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

HF_TOKEN = ""

MINIMAL_REPOS = [
    "Qwen/Qwen3-14B-Instruct",
    "black-forest-labs/FLUX.1-schnell",
    "hexgrad/Kokoro-82M",
]

ALL_REPOS = [
    "Qwen/Qwen3-14B-Instruct",
    "Sao10K/Fimbulvetr-11B-v2",
    "sophosympatheia/Midnight-Miqu-70B-v1.5",
    "deepseek-ai/DeepSeek-V3",
    "black-forest-labs/FLUX.1.1-pro-ultra",
    "black-forest-labs/FLUX.1-dev",
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-3.5-large",
    "stabilityai/stable-diffusion-3.5-medium",
    "stabilityai/stable-diffusion-3.5-large-turbo",
    "Wan-AI/Wan2.2-T2V-A14B-Diffusers",
    "genmo/mochi-1.5-final",
    "Lightricks/LTX-2",
    "THUDM/CogVideoX-5b",
    "Tencent/HunyuanVideo",
    "hexgrad/Kokoro-82M",
    "OpenMOSS-Team/MOSS-VoiceGenerator",
]


def _safe_repo_dirname(repo_id: str) -> str:
    s = repo_id.strip().replace("/", "__")
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    return s[:120] or "model"


def _resolve_token(cli_token: str | None) -> str | None:
    if cli_token and str(cli_token).strip():
        return str(cli_token).strip()
    if HF_TOKEN and str(HF_TOKEN).strip():
        return str(HF_TOKEN).strip()
    for key in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN"):
        t = os.environ.get(key)
        if t and str(t).strip():
            return str(t).strip()
    return None


def download_one(repo_id: str, *, out_root: Path, token: str | None, max_workers: int) -> Path:
    from huggingface_hub import snapshot_download

    out_root.mkdir(parents=True, exist_ok=True)
    local_dir = out_root / _safe_repo_dirname(repo_id)
    local_dir.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        token=token,
        max_workers=max_workers,
        etag_timeout=float(os.environ.get("HF_ETAG_TIMEOUT", "30")),
    )
    return local_dir


def main() -> int:
    p = argparse.ArgumentParser(description="Download HF models (embedded in download_all_for_transfer.ps1).")
    p.add_argument("--out", type=Path, default=Path("models"))
    p.add_argument("--token", default=None)
    p.add_argument("--all", action="store_true")
    p.add_argument(
        "--max-workers",
        type=int,
        default=max(1, min(32, int(os.environ.get("HF_SNAPSHOT_MAX_WORKERS", "8")))),
    )
    args = p.parse_args()

    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        print("Install:  pip install huggingface_hub tqdm", file=sys.stderr)
        return 1

    token = _resolve_token(args.token)
    repos = ALL_REPOS if args.all else MINIMAL_REPOS
    seen: set[str] = set()
    repos = [r for r in repos if not (r in seen or seen.add(r))]

    out_root = args.out.expanduser().resolve()
    cwd = Path.cwd().resolve()
    print(f"Working directory: {cwd}")
    print(f"Models folder:      {out_root}")
    print(f"Models to fetch: {len(repos)} ({'full curated' if args.all else 'minimal'})")
    print(f"HF token: {'set' if token else 'NOT SET — gated models will fail without token/access'}")
    print(
        "Note: first large weight file can take a long time; progress may look stuck briefly.\n",
    )

    failed: list[str] = []
    for i, rid in enumerate(repos, 1):
        print(f"[{i}/{len(repos)}] {rid}")
        try:
            path = download_one(rid, out_root=out_root, token=token, max_workers=args.max_workers)
            print(f"  -> {path}")
        except Exception as e:
            failed.append(f"{rid}: {e}")
            print(f"  !! FAILED: {e}")

    print("Done.")
    if failed:
        print("\nFailures:")
        for f in failed:
            print(f"  - {f}")
        print("\nFor gated Llama models: accept the license on Hugging Face and use a token with access.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $PyHfDownload -Encoding UTF8

Write-Host "Script folder:  $ScriptRoot"
Write-Host "Repo root:      $RepoRoot"
Write-Host "Models output:  $ModelsOut"
Write-Host "Transcript:     $TranscriptPath"
Write-Host ""

if (-not (Test-Path -LiteralPath $ModelsOut)) {
    New-Item -ItemType Directory -Path $ModelsOut -Force | Out-Null
    Write-Host "Created models folder: $ModelsOut"
}

$env:AQUADUCT_ROOT = $RepoRoot

Start-Transcript -Path $TranscriptPath -Encoding UTF8
try {
    $VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Host "=== Creating virtual environment (.venv) ==="
        & python -m venv (Join-Path $RepoRoot ".venv")
        if ($LASTEXITCODE -ne 0) { throw "python -m venv failed" }
        $VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    }
    else {
        Write-Host "=== Using existing .venv ==="
    }

    Write-Host "=== pip: upgrade pip / setuptools / wheel ==="
    & $VenvPython -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

    Write-Host "=== PyTorch + requirements (embedded bootstrap -> src.torch_install) ==="
    & $VenvPython $PyTorchBootstrap --with-rest
    if ($LASTEXITCODE -ne 0) { throw "torch install failed" }

    Write-Host "=== Hugging Face snapshots (full curated list) -> $ModelsOut ==="
    & $VenvPython $PyHfDownload --all --out $ModelsOut
    if ($LASTEXITCODE -ne 0) { throw "HF download failed" }

    Write-Host ""
    Write-Host "=== Done. ==="
    Write-Host "Weights: $ModelsOut — copy to other PC under <repo>\.Aquaduct_data\models\"
    Write-Host "Full log: $TranscriptPath"
}
finally {
    Stop-Transcript
    Remove-Item -LiteralPath $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:AQUADUCT_ROOT -ErrorAction SilentlyContinue
}

exit $LASTEXITCODE
