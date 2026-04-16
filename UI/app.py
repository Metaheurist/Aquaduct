"""Application entry: QApplication + theme + main window."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from UI.main_window import MainWindow
from UI.theme import TIKTOK_QSS, build_qss, resolve_palette
from src.single_instance import single_instance_guard
from src.ui_settings import load_settings


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
    single_instance_guard()
    # Load HF_TOKEN (and other env vars) from repo `.env` for authenticated downloads.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass
    app = QApplication(sys.argv)
    # Windows native style often ignores QSS colors inside QSpinBox/QComboBox; Fusion paints consistently.
    app.setStyle("Fusion")
    # Apply saved branding theme if enabled (fallback to default).
    try:
        settings = load_settings()
        pal = resolve_palette(getattr(settings, "branding", None))
        app.setStyleSheet(build_qss(pal))
    except Exception:
        app.setStyleSheet(TIKTOK_QSS)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
