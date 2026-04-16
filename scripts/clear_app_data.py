"""
CLI equivalent of the desktop app: Settings → Danger zone → "Clear data".

Deletes ui_settings.json, models/, data/news_cache/, .cache/, runs/, videos/,
then recreates empty folders and writes a fresh default ui_settings.json.

Close the app (and any Explorer windows in this repo) before running.

Usage:
  python scripts/clear_app_data.py          # prompts for confirmation
  python scripts/clear_app_data.py -y       # no prompt (automation)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import AppSettings, get_paths
from src.fs_delete import rmtree_robust, unlink_file
from src.ui_settings import save_settings, settings_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wipe local app data (same as the UI Clear data button).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation (use for scripts).",
    )
    args = parser.parse_args()

    paths = get_paths()
    sp = settings_path()

    lines = [
        "This will delete:",
        f"  - {sp} (settings)",
        f"  - {paths.models_dir} (downloaded models)",
        f"  - {paths.news_cache_dir} (topic cache)",
        f"  - {paths.cache_dir} (ffmpeg + other caches)",
        f"  - {paths.runs_dir}",
        f"  - {paths.videos_dir}",
        "",
        "Then empty folders are recreated and default settings are saved.",
        "This cannot be undone.",
    ]
    print("\n".join(lines))

    if not args.yes:
        try:
            reply = input("\nType YES to continue, or anything else to abort: ").strip()
        except EOFError:
            reply = ""
        if reply != "YES":
            print("Aborted.")
            sys.exit(1)

    errors: list[str] = []

    uerr = unlink_file(sp)
    if uerr:
        errors.append(uerr)

    for folder in (
        paths.models_dir,
        paths.news_cache_dir,
        paths.cache_dir,
        paths.runs_dir,
        paths.videos_dir,
    ):
        rerr = rmtree_robust(folder)
        if rerr:
            errors.append(rerr)

    try:
        paths.models_dir.mkdir(parents=True, exist_ok=True)
        paths.news_cache_dir.mkdir(parents=True, exist_ok=True)
        paths.cache_dir.mkdir(parents=True, exist_ok=True)
        paths.runs_dir.mkdir(parents=True, exist_ok=True)
        paths.videos_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        errors.append(f"Recreate folders: {e}")

    fresh = AppSettings()
    try:
        save_settings(fresh)
    except OSError as e:
        errors.append(f"Save default settings: {e}")

    if errors:
        print("\nFinished with errors:")
        for e in errors:
            print(f"  - {e}")
        print(
            "\nTip: Close the app, close Explorer windows under this repo, "
            "wait a few seconds, then run again."
        )
        sys.exit(2)

    print("\nAll local data cleared. Default ui_settings.json written. Restart the app for a clean slate.")


if __name__ == "__main__":
    main()
