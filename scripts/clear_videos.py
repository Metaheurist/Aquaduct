"""
Delete everything under repo `videos/` and recreate an empty folder.

Close Aquaduct and Explorer windows inside `videos/` first if you see WinError 32.

Usage:
  python scripts/clear_videos.py
  python scripts/clear_videos.py -y
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
    parser = argparse.ArgumentParser(description="Remove all generated outputs under videos/.")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    err = clear_path_robust(get_paths().videos_dir, label="videos/", skip_confirm=args.yes)
    if err == "aborted":
        sys.exit(1)
    if err is not None:
        print(
            "\nCould not fully clear videos/ (files still locked).\n"
            "Close the app, close Explorer under videos/, then run:\n"
            "  python scripts/clear_videos.py -y"
        )
        sys.exit(2)

    print("videos/ cleared (empty folder recreated).")


if __name__ == "__main__":
    main()
