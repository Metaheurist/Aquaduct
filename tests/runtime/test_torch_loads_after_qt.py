from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("torch") is None or importlib.util.find_spec("PyQt6") is None,
    reason="needs torch and PyQt6",
)


def test_torch_imports_after_ui_app_starts_qt() -> None:
    """Desktop launch order (UI.app, then QApplication, then torch) must not break torch.

    Runs in a fresh interpreter: tests/conftest.py preloads torch, which would hide the bug.
    """
    code = (
        "import UI.app\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "import torch\n"
        "print('TORCH_OK', torch.__version__)\n"
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    r = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, timeout=240
    )
    assert "TORCH_OK" in r.stdout, (r.stdout + r.stderr)[-2000:]
