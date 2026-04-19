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
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import get_paths
from src.util.fs_delete import rmtree_robust


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove all generated outputs under videos/.")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    p = get_paths().videos_dir
    print(f"Target: {p}")

    if not args.yes:
        try:
            r = input("Delete ALL contents of videos/? Type YES: ").strip()
        except EOFError:
            r = ""
        if r != "YES":
            print("Aborted.")
            sys.exit(1)

    for attempt in range(1, 6):
        err = rmtree_robust(p, attempts=10, base_delay_s=0.25)
        if err is None:
            if not p.exists():
                break
            try:
                if not any(p.iterdir()):
                    break
            except OSError:
                break
        print(f"Attempt {attempt}: {err}")
        time.sleep(1.5)

    p.mkdir(parents=True, exist_ok=True)

    try:
        still_has_files = p.exists() and any(p.iterdir())
    except OSError:
        still_has_files = True

    if still_has_files:
        print(
            "\nCould not fully clear videos/ (files still locked).\n"
            "Close the app, close Explorer under videos/, then run:\n"
            "  python scripts/clear_videos.py -y"
        )
        sys.exit(2)

    print("videos/ cleared (empty folder recreated).")


if __name__ == "__main__":
    main()
