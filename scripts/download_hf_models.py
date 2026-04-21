#!/usr/bin/env python3
"""
Download Aquaduct Hugging Face model snapshots into ./models (same layout as the app).

Each repo is stored under models/<repo_id with slashes replaced>, matching
src/model_manager.download_model_to_project().

Run from the repo root (e.g. your Aquaduct clone or a USB drive copy):
  cd D:\\path\\to\\Aquaduct
  pip install huggingface_hub tqdm
  # optional: paste token in HF_TOKEN below, or set HF_TOKEN=hf_... in the shell
  python scripts/download_hf_models.py

  # downloads to .\\models\\...

Override the models folder:
  python scripts/download_hf_models.py --out D:\\models

Gated models (e.g. meta-llama/*) require a token with access approved on huggingface.co.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Paste your Hugging Face token here (e.g. hf_...). Leave empty to use --token or env instead.
# Precedence: --token CLI > this variable > HF_TOKEN / HUGGINGFACEHUB_API_TOKEN env.
HF_TOKEN = ""

# Same defaults as src/config.py get_models()
MINIMAL_REPOS = [
    "Qwen/Qwen3-14B-Instruct",
    "black-forest-labs/FLUX.1-schnell",
    "hexgrad/Kokoro-82M",
]

# Same repo ids as src/models/model_manager.py model_options() (dedupe order-preserving)
ALL_REPOS = [
    # Script (LLM)
    "Qwen/Qwen3-14B-Instruct",
    "Sao10K/Fimbulvetr-11B-v2",
    "sophosympatheia/Midnight-Miqu-70B-v1.5",
    "deepseek-ai/DeepSeek-V3",
    # Image (T2I)
    "black-forest-labs/FLUX.1.1-pro-ultra",
    "black-forest-labs/FLUX.1-dev",
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-3.5-large",
    "stabilityai/stable-diffusion-3.5-medium",
    "stabilityai/stable-diffusion-3.5-large-turbo",
    # Video / motion
    "Wan-AI/Wan2.2-T2V-A14B-Diffusers",
    "genmo/mochi-1.5-final",
    "Lightricks/LTX-2",
    "THUDM/CogVideoX-5b",
    "Tencent/HunyuanVideo",
    # Voice (TTS)
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
    p = argparse.ArgumentParser(
        description="Download HF models into ./models (same layout as Aquaduct app).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("models"),
        help="Models directory (default: ./models under the current working directory)",
    )
    p.add_argument(
        "--token",
        default=None,
        help="Hugging Face token (overrides HF_TOKEN in script and env vars)",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Download full curated list (~many GB). Default is minimal 3-model set.",
    )
    p.add_argument(
        "--max-workers",
        type=int,
        default=max(1, min(32, int(os.environ.get("HF_SNAPSHOT_MAX_WORKERS", "8")))),
        help="Parallel file downloads (default 8)",
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
