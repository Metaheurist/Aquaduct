"""
Launcher script (lives next to the rest of the UI package).

Run from repo root:

  python UI/ui_app.py

Prefer:

  python -m UI
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _debug_flags_present() -> bool:
    return any(a.lower() in ("-debug", "--debug") for a in sys.argv[1:])


def _strip_debug_args() -> None:
    if not _debug_flags_present():
        return
    sys.argv = [sys.argv[0]] + [
        a for a in sys.argv[1:] if a.lower() not in ("-debug", "--debug")
    ]


def _maybe_attach_debug_console() -> None:
    """Frozen Windows EXE: allocate a console only when launched with -debug/--debug."""
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return
    if not _debug_flags_present():
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        if kernel32.GetConsoleWindow() == 0:
            kernel32.AllocConsole()
        con = open(  # noqa: SIM115
            "CONOUT$",
            "w",
            encoding="utf-8",
            errors="replace",
            buffering=1,
        )
        sys.stdout = con
        sys.stderr = con
    except OSError:
        pass


# Repo root = parent of the `UI/` directory
_ROOT = Path(__file__).resolve().parent.parent
try:
    os.chdir(_ROOT)
except OSError:
    pass
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_maybe_attach_debug_console()
_strip_debug_args()

from UI.app import main

if __name__ == "__main__":
    main()
