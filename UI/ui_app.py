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

# Repo root = parent of the `UI/` directory
_ROOT = Path(__file__).resolve().parent.parent
try:
    os.chdir(_ROOT)
except OSError:
    pass
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from UI.app import main

if __name__ == "__main__":
    main()
