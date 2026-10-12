#!/usr/bin/env python3
"""
Render every main-window tab to PNG for the docs (default settings, isolated app data).

Uses a throwaway ``.Aquaduct_data`` under a temp folder so no real keys, topics, or paths
appear in the images, and disables startup network probes and first-run prompts.

  python scripts/capture_ui_screenshots.py                 # writes docs/images/ui/*.png
  python scripts/capture_ui_screenshots.py --out some/dir  # custom output folder
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_") or "tab"


def _isolate_app_data(root: Path) -> None:
    import src.content.llm_chat_rag as rag
    import src.core.app_dirs as app_dirs
    import src.core.config as config
    import src.runtime.pipeline_queue_store as queue_store
    import src.settings.secrets_crypto as secrets_crypto
    import src.settings.ui_settings as ui_settings

    for mod in (app_dirs, config, ui_settings, queue_store, secrets_crypto, rag):
        mod.application_data_dir = lambda: root  # type: ignore[attr-defined]


def _quiet_startup() -> None:
    import src.util.network_status as network_status
    import UI.workers.models as worker_models
    from UI.main_window import MainWindow

    network_status.is_internet_likely_reachable = lambda *_a, **_k: True
    worker_models.ModelSizePingWorker.run = lambda self: self.done.emit({})
    MainWindow._toast = lambda self, *_a, **_k: None
    for name in ("_maybe_prompt_hf_token", "_maybe_show_first_run_tutorial", "_start_chat_docs_index_build"):
        setattr(MainWindow, name, lambda self: None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=REPO / "docs" / "images" / "ui")
    args = parser.parse_args()

    try:
        import torch  # noqa: F401  (load torch DLLs before Qt on Windows)
    except Exception:
        pass

    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    with tempfile.TemporaryDirectory(prefix="aquaduct_ss_") as tmp:
        root = Path(tmp)
        _isolate_app_data(root)
        _quiet_startup()

        from src.core.config import AppSettings
        from src.settings.ui_settings import save_settings
        from UI.theme import build_qss, resolve_palette, set_active_palette

        settings = AppSettings()
        save_settings(settings)
        pal = resolve_palette(settings.branding)
        app.setStyleSheet(build_qss(pal))
        set_active_palette(pal)

        from UI.main_window import MainWindow

        win = MainWindow()
        win.show()
        win._ensure_all_tabs_built()
        for _ in range(10):
            app.processEvents()
        # Persist widget defaults to the temp settings so the title bar shows no unsaved marker.
        win._save_settings()
        app.processEvents()

        args.out.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for i in range(win.tabs.count()):
            win.tabs.setCurrentIndex(i)
            for _ in range(10):
                app.processEvents()
            name = f"{i + 1:02d}_{_slug(win.tabs.tabText(i))}.png"
            path = args.out / name
            win.grab().save(str(path), "PNG")
            written.append(path)

        # hide(), not close(): closeEvent would prompt to save the throwaway settings.
        win.hide()
        app.processEvents()

    for p in written:
        print(p.relative_to(REPO) if p.is_relative_to(REPO) else p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
