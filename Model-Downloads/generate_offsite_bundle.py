"""
Write a standalone offsite bundle under Model-Downloads/offsite/.

The generated downloader reads HF_TOKEN / HUGGINGFACEHUB_API_TOKEN from the
environment at runtime (optional: repo-root .env on the target machine).
Tokens are never embedded into generated scripts.

Run from repo root:
  python Model-Downloads/generate_offsite_bundle.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = Path(__file__).resolve().parent / "offsite"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except Exception:
        pass


def _hf_token_from_env() -> str:
    _load_dotenv()
    for key in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN"):
        t = (os.environ.get(key) or "").strip()
        if t:
            return t
    return ""


def _curated_repo_ids() -> list[str]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.models.model_manager import model_options

    seen: set[str] = set()
    out: list[str] = []
    for o in model_options():
        for rid in (o.repo_id, getattr(o, "pair_image_repo_id", "") or ""):
            rid = str(rid).strip()
            if rid and rid not in seen:
                seen.add(rid)
                out.append(rid)
    return out


def _safe_repo_dirname(repo_id: str) -> str:
    s = repo_id.strip().replace("/", "__")
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    return (s[:120] or "model")


def _render_standalone(*, repo_ids: list[str]) -> str:
    repos_literal = json.dumps(repo_ids, indent=4)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aquaduct curated model snapshots — standalone downloader (generated).

Generated: {ts}

Set HF_TOKEN or HUGGINGFACEHUB_API_TOKEN in the environment before running
(or place a .env file next to this script). Tokens are never stored in this file.

Copies layout: ./models/<safe_repo_dir>/  (same as Aquaduct download_model_to_project).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_IDS = {repos_literal}


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent / ".env")
    except Exception:
        pass


def _hf_token_from_env() -> str:
    _load_dotenv()
    for key in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN"):
        t = (os.environ.get(key) or "").strip()
        if t:
            return t
    return ""


def _safe_repo_dirname(repo_id: str) -> str:
    s = repo_id.strip().replace("/", "__")
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    return (s[:120] or "model")


def main() -> int:
    root = Path(__file__).resolve().parent
    models_dir = root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    tok = _hf_token_from_env()
    if not tok:
        print(
            "Set HF_TOKEN or HUGGINGFACEHUB_API_TOKEN in the environment "
            "(or add a .env file beside this script).",
            file=sys.stderr,
        )
        return 2

    os.environ.setdefault("HF_TOKEN", tok)
    os.environ.setdefault("HUGGINGFACEHUB_API_TOKEN", tok)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Install: pip install -r requirements-offsite.txt", file=sys.stderr)
        return 2

    try:
        from tqdm.auto import tqdm as tqdm_class
    except Exception:
        tqdm_class = None  # type: ignore[assignment]

    max_workers = max(1, min(32, int(os.environ.get("HF_SNAPSHOT_MAX_WORKERS", "8"))))

    failed: list[str] = []
    print(f"Destination: {{models_dir.resolve()}}")
    print(f"Repositories: {{len(REPO_IDS)}}")
    for rid in REPO_IDS:
        local_dir = models_dir / _safe_repo_dirname(rid)
        local_dir.mkdir(parents=True, exist_ok=True)
        print(f"\\n=== {{rid}} ===> {{local_dir.name}}")
        try:
            snapshot_download(
                repo_id=rid,
                local_dir=str(local_dir),
                tqdm_class=tqdm_class,
                token=tok,
                max_workers=max_workers,
                etag_timeout=float(os.environ.get("HF_ETAG_TIMEOUT", "30")),
            )
        except Exception as e:
            failed.append(f"{{rid}}: {{e}}")
            print(f"FAILED: {{e}}", file=sys.stderr)

    print("\\nDone.")
    if failed:
        print("\\nSome downloads failed:", file=sys.stderr)
        for f in failed:
            print(f"  - {{f}}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def main() -> int:
    repo_ids = _curated_repo_ids()
    if not repo_ids:
        print("No curated repo ids (model_options() empty?).", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    script_path = OUT_DIR / "download_all_models.py"
    req_path = OUT_DIR / "requirements-offsite.txt"

    body = _render_standalone(repo_ids=repo_ids)
    script_path.write_text(body, encoding="utf-8")
    req_path.write_text(
        "huggingface_hub>=0.20.0\ntqdm>=4.60.0\npython-dotenv>=1.0.0\n",
        encoding="utf-8",
    )

    token_present = bool(_hf_token_from_env())
    print(f"Wrote: {script_path}")
    print(f"Wrote: {req_path}")
    print(f"Repositories: {len(repo_ids)}")
    if token_present:
        print("HF token detected in current environment (not written into the bundle).")
    else:
        print("No HF token in current environment — set one on the target machine before downloading.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
