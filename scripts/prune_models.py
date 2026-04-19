"""
Delete everything under `models/` except folders for the Hugging Face repos you keep.

Folder layout matches downloads: `models/<owner>__<name>/` (see `src/model_manager.py`).

Examples:
  # Match current Model tab (reads ui_settings.json — close the app first if it locks files)
  python scripts/prune_models.py --from-settings --dry-run
  python scripts/prune_models.py --from-settings -y

  # Keep the "Qwen 1.5B + SVD XT + SDXL Turbo + Kokoro" set from the default UI picks
  python scripts/prune_models.py --preset qwen-svd-kokoro --dry-run
  python scripts/prune_models.py --preset qwen-svd-kokoro -y

  # Explicit repo ids (repeat --keep)
  python scripts/prune_models.py -y --keep Qwen/Qwen2.5-1.5B-Instruct --keep hexgrad/Kokoro-82M
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import AppSettings, get_paths
from src.util.fs_delete import rmtree_robust, unlink_file
from src.models.model_manager import project_model_dirname
from src.settings.ui_settings import load_settings

# Screenshot defaults: Qwen2.5 1.5B, SVD+SDXL pair, Kokoro 82M
PRESETS: dict[str, list[str]] = {
    "qwen-svd-kokoro": [
        "Qwen/Qwen2.5-1.5B-Instruct",
        "stabilityai/stable-video-diffusion-img2vid-xt",
        "stabilityai/sdxl-turbo",
        "hexgrad/Kokoro-82M",
    ],
}


def _repos_from_settings(settings: AppSettings) -> list[str]:
    out: list[str] = []
    for v in (settings.llm_model_id, settings.image_model_id, settings.video_model_id, settings.voice_model_id):
        s = (v or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove model folders under models/ except selected repos.")
    parser.add_argument(
        "--from-settings",
        action="store_true",
        help="Keep repos referenced in ui_settings.json (llm, image, video, voice).",
    )
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS.keys()),
        help="Keep a fixed list of repos (see script docstring).",
    )
    parser.add_argument(
        "--keep",
        action="append",
        default=[],
        metavar="ORG/NAME",
        help="Additional HF repo id to preserve (repeatable).",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    parser.add_argument("--dry-run", action="store_true", help="Print actions only")
    args = parser.parse_args()

    keep_repos: list[str] = []
    if args.preset:
        keep_repos.extend(PRESETS[args.preset])
    if args.from_settings:
        keep_repos.extend(_repos_from_settings(load_settings()))
    for k in args.keep:
        s = (k or "").strip()
        if s and s not in keep_repos:
            keep_repos.append(s)

    # De-duplicate preserving order
    seen: set[str] = set()
    keep_repos = [x for x in keep_repos if not (x in seen or seen.add(x))]

    if not keep_repos:
        print(
            "No repos to keep. Use --from-settings, --preset, or --keep ORG/NAME.\n"
            "Example: python scripts/prune_models.py --preset qwen-svd-kokoro --dry-run"
        )
        sys.exit(1)

    keep_names = {project_model_dirname(r) for r in keep_repos}
    models_dir = get_paths().models_dir
    print(f"models dir: {models_dir}")
    print("Keeping folders:")
    for r in keep_repos:
        print(f"  {r}  ->  {project_model_dirname(r)}")

    to_remove: list[Path] = []
    if not models_dir.exists():
        print("Nothing to do (models dir missing).")
        return

    for child in sorted(models_dir.iterdir()):
        if child.name in keep_names:
            continue
        to_remove.append(child)

    if not to_remove:
        print("Nothing to remove (no extra folders/files).")
        return

    print("\nWould delete:")
    for p in to_remove:
        print(f"  {p}")

    if args.dry_run:
        print("\nDry run only.")
        return

    if not args.yes:
        try:
            r = input("\nDelete the above? Type YES: ").strip()
        except EOFError:
            r = ""
        if r != "YES":
            print("Aborted.")
            sys.exit(1)

    errors: list[str] = []
    for p in to_remove:
        if p.is_dir():
            err = rmtree_robust(p, attempts=10, base_delay_s=0.25)
            if err:
                errors.append(f"{p}: {err}")
                time.sleep(1.0)
        else:
            err = unlink_file(p)
            if err:
                errors.append(f"{p}: {err}")

    if errors:
        print("\nSome paths could not be removed (close the app / Explorer / downloads, then retry):")
        for e in errors:
            print(f"  {e}")
        sys.exit(2)

    print("\nDone. Kept only the listed model folders.")


if __name__ == "__main__":
    main()
