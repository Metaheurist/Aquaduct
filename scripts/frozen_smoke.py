"""
Import smoke for desktop UI: dev interpreter or built EXE.

Dev (repo root venv):

  python scripts/frozen_smoke.py

After PyInstaller UI build (onedir default name):

  python scripts/frozen_smoke.py --exe dist\\aquaduct-ui\\aquaduct-ui.exe

One-file:

  python scripts/frozen_smoke.py --exe dist\\aquaduct-ui.exe

The EXE path uses env AQUADUCT_IMPORT_SMOKE=1 (see UI/ui_app.py early exit).
"""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path

_MODULES = (
    "main",
    "src.runtime.pipeline_api",
    "src.runtime.generation_facade",
    "UI.workers",
    "UI.api_model_widgets",
    "UI.app",
)


def _run_dev() -> int:
    for name in _MODULES:
        importlib.import_module(name)
    print("frozen_smoke: dev imports OK", flush=True)
    return 0


def _run_exe(exe: Path) -> int:
    if not exe.is_file():
        print(f"frozen_smoke: missing exe: {exe}", file=sys.stderr, flush=True)
        return 2
    env = {**os.environ, "AQUADUCT_IMPORT_SMOKE": "1"}
    proc = subprocess.run([str(exe)], env=env, cwd=str(exe.parent))
    return int(proc.returncode)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="Import smoke for Aquaduct UI (dev or frozen EXE).")
    p.add_argument(
        "--exe",
        type=Path,
        default=None,
        help="Path to built aquaduct-ui.exe (sets AQUADUCT_IMPORT_SMOKE for headless import exit).",
    )
    args = p.parse_args()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if args.exe is None:
        return _run_dev()
    return _run_exe(args.exe.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
