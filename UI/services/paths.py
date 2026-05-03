"""Project root resolution (directory containing ``requirements.txt``, ``src/``, ``UI/``)."""

from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    # This file lives at ``<repo>/UI/services/paths.py`` (also under PyInstaller extract root).
    if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None):
        base = Path(sys._MEIPASS)  # type: ignore[arg-type]
        if (base / "requirements.txt").is_file():
            return base
    here = Path(__file__).resolve()
    return here.parents[2]
