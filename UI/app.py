"""Application entry: QApplication + theme + main window."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from UI.main_window import MainWindow
from UI.theme import TIKTOK_QSS


def _ensure_project_root_on_path() -> None:
    # `UI/app.py` -> parent is `UI/`, grandparent is repo root
    root = Path(__file__).resolve().parent.parent
    try:
        os.chdir(root)
    except OSError:
        pass
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main() -> None:
    _ensure_project_root_on_path()
    app = QApplication(sys.argv)
    app.setStyleSheet(TIKTOK_QSS)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
