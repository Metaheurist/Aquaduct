"""
Launcher script (lives next to the rest of the UI package).

Run from repo root:

  python UI/ui_app.py

Prefer:

  python -m UI
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _apply_debug_categories_from_argv() -> None:
    """``--debug pipeline,ui`` or ``--debug=all`` — merged with env (see ``debug.debug_log``)."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--debug", type=str, default="")
    args, rest = p.parse_known_args(sys.argv[1:])
    sys.argv = [sys.argv[0]] + rest
    if args.debug:
        from debug import apply_cli_debug

        apply_cli_debug(args.debug)


def _debug_flags_present() -> bool:
    return any(a.lower() in ("-debug", "--debug") for a in sys.argv[1:])


def _strip_debug_args() -> None:
    """Remove -debug/--debug (console flag) and optional ``--debug <categories>`` value from argv before Qt."""
    out: list[str] = []
    i = 0
    argv = sys.argv[1:]
    while i < len(argv):
        a = argv[i]
        low = a.lower()
        if low in ("-debug", "--debug"):
            # Optional next token if it is not another flag (category list for debug.debug_log).
            j = i + 1
            if j < len(argv) and not str(argv[j]).startswith("-"):
                i = j + 1
            else:
                i += 1
            continue
        out.append(a)
        i += 1
    sys.argv = [sys.argv[0]] + out


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

_apply_debug_categories_from_argv()
_maybe_attach_debug_console()
_strip_debug_args()

from UI.app import main

if __name__ == "__main__":
    main()
