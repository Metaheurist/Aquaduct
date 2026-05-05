"""
Delete everything under repo `models/` and recreate an empty folder.

If you see WinError 32, something still has files open:
  - Quit Aquaduct
  - Stop any `python scripts/download_hf_models.py` (Ctrl+C)
  - Close Explorer windows inside `models/`
Then run this again.

Usage:
  python scripts/clear_models.py
  python scripts/clear_models.py -y
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._common import clear_path_robust, ensure_repo_on_path

ensure_repo_on_path(root=ROOT)

from src.core.config import get_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove all downloaded models under models/.")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    err = clear_path_robust(get_paths().models_dir, label="models/", skip_confirm=args.yes)
    if err == "aborted":
        sys.exit(1)
    if err is not None:
        print(
            "\nCould not fully clear models/ (files still locked).\n"
            "Close the app and any download scripts, then run:\n"
            f"  python scripts/clear_models.py -y"
        )
        sys.exit(2)

    print("models/ cleared (empty folder recreated).")


if __name__ == "__main__":
    main()
