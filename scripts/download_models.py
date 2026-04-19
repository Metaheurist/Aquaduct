from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running as a script from repo root without installing as a package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Same as the desktop app: load HF_TOKEN / HUGGINGFACEHUB_API_TOKEN from repo `.env`.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from src.core.config import get_paths
from src.models.model_manager import download_model_to_project, model_options


def main() -> None:
    paths = get_paths()
    paths.models_dir.mkdir(parents=True, exist_ok=True)
    opts = model_options()

    tok = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN") or "").strip()
    print(f"HF token: {'set (higher rate limits)' if tok else 'NOT SET — add HF_TOKEN to .env for faster downloads'}")
    print(
        "\nProgress note: the bar counts completed files (e.g. 10/10). After the first small files,\n"
        "the next item is often a multi‑GB weights file — the percentage can sit at ~10% for a long time\n"
        "while that file downloads (watch for a second tqdm bar or network activity).\n"
    )
    print(f"Downloading {len(opts)} model snapshots into: {paths.models_dir}")
    failed: list[str] = []
    for opt in opts:
        print(f"- {opt.kind}: {opt.repo_id} ({opt.speed})")
        try:
            local = download_model_to_project(opt.repo_id, models_dir=paths.models_dir)
            print(f"  -> {local}")
        except Exception as e:
            msg = f"{opt.repo_id}: {e}"
            failed.append(msg)
            print(f"  !! FAILED: {e}")

    print("Done.")
    if failed:
        print("\nSome downloads failed:")
        for f in failed:
            print(f"- {f}")
        print("\nIf the failure is a gated model, set HF_TOKEN (or login) and re-run.")


if __name__ == "__main__":
    main()

