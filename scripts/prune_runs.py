"""
Delete old folders under ``runs/`` while keeping the newest N workspaces.

Examples:
  python scripts/prune_runs.py --keep-last 5 --dry-run
  python scripts/prune_runs.py --keep-last 3 -y

  # Also preserve the run tied to resume_partial_project_directory in ui_settings.json
  python scripts/prune_runs.py --from-settings --keep-last 2 -y
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
from src.settings.ui_settings import load_settings
from src.util.fs_delete import rmtree_robust, unlink_file


def _runs_to_keep(*, keep_last: int, from_settings: bool) -> set[Path]:
    runs_dir = get_paths().runs_dir
    keep: set[Path] = set()
    if not runs_dir.is_dir():
        return keep
    children = [p for p in runs_dir.iterdir() if p.is_dir()]
    children.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0.0, reverse=True)
    for p in children[: max(0, int(keep_last))]:
        keep.add(p.resolve())
    if from_settings:
        try:
            s = load_settings()
            rp = str(getattr(s, "resume_partial_project_directory", "") or "").strip()
            if rp:
                cand = Path(rp).expanduser().resolve()
                if cand.is_dir():
                    keep.add(cand)
                    parent = cand.parent
                    if parent.is_dir() and parent.parent.resolve() == runs_dir.resolve():
                        keep.add(parent.resolve())
        except Exception:
            pass
    return keep


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove old run workspaces under runs/.")
    parser.add_argument(
        "--keep-last",
        type=int,
        default=3,
        metavar="N",
        help="Preserve the N most recently modified run folders (default: 3).",
    )
    parser.add_argument(
        "--from-settings",
        action="store_true",
        help="Also keep the folder from resume_partial_project_directory in ui_settings.json.",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    parser.add_argument("--dry-run", action="store_true", help="Print actions only")
    args = parser.parse_args()

    runs_dir = get_paths().runs_dir
    print(f"runs dir: {runs_dir}")
    keep = _runs_to_keep(keep_last=args.keep_last, from_settings=bool(args.from_settings))
    if keep:
        print("Keeping:")
        for p in sorted(keep, key=lambda x: x.name):
            print(f"  {p}")

    if not runs_dir.is_dir():
        print("Nothing to do (runs dir missing).")
        return

    to_remove: list[Path] = []
    for child in sorted(runs_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.resolve() in keep:
            continue
        to_remove.append(child)

    if not to_remove:
        print("Nothing to remove.")
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
        err = rmtree_robust(p, attempts=10, base_delay_s=0.25)
        if err:
            errors.append(f"{p}: {err}")
            time.sleep(1.0)
        elif p.exists() and p.is_file():
            err2 = unlink_file(p)
            if err2:
                errors.append(f"{p}: {err2}")

    if errors:
        print("\nSome paths could not be removed (close the app / Explorer, then retry):")
        for e in errors:
            print(f"  {e}")
        sys.exit(2)

    print("\nDone.")


if __name__ == "__main__":
    main()
