"""
Writable log files under ``<install>/logs/`` (repo root in development; next to the exe when frozen).
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from src.core.app_dirs import installation_dir

_lock = threading.Lock()


def logs_dir() -> Path:
    """Ensures ``logs/`` exists and returns it."""
    d = installation_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def append_ui_log(line: str) -> None:
    """Append one line to ``logs/ui.log`` (Model tab activity log mirror)."""
    text = (line or "").rstrip()
    if not text:
        return
    p = logs_dir() / "ui.log"
    ts = datetime.now().isoformat(timespec="seconds")
    with _lock:
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {text}\n")


def append_debug_log(line: str) -> None:
    """Append one line to ``logs/debug.log`` (mirror of categorized stderr debug)."""
    text = (line or "").rstrip()
    if not text:
        return
    p = logs_dir() / "debug.log"
    with _lock:
        with p.open("a", encoding="utf-8") as f:
            f.write(text + "\n")


def write_install_dependencies_log(content: str, *, prefix: str = "install-dependencies") -> Path:
    """Write a full session log for Model → Install dependencies; returns the file path."""
    logs_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    p = logs_dir() / f"{prefix}-{stamp}.log"
    with p.open("w", encoding="utf-8") as f:
        f.write(content or "")
    return p


def default_install_pytorch_log_path() -> Path:
    """Default path for CLI / PowerShell install-pytorch streaming log."""
    return logs_dir() / "install-pytorch.log"
