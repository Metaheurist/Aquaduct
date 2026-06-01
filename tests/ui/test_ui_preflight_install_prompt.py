"""Pre-run dependency install prompt (UI modernization Tier 3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.runtime.preflight import PreflightResult


@pytest.mark.qt
def test_offer_runtime_install_user_declines(monkeypatch, qapplication):
    from PyQt6.QtWidgets import QWidget

    from UI.main_window import MainWindow

    w = QWidget()
    pf = PreflightResult(
        ok=False,
        errors=["Missing Python packages: numpy, scipy"],
        warnings=[],
    )
    monkeypatch.setattr(
        "UI.dialogs.frameless_dialog.aquaduct_question",
        lambda *a, **k: False,
    )
    assert MainWindow._offer_runtime_install_for_preflight(w, pf) is False


@pytest.mark.qt
def test_offer_runtime_install_success(monkeypatch, qapplication):
    from PyQt6.QtWidgets import QWidget

    from UI.main_window import MainWindow

    w = QWidget()
    pf = PreflightResult(
        ok=False,
        errors=["Missing Python packages: numpy"],
        warnings=[],
    )
    monkeypatch.setattr(
        "UI.dialogs.frameless_dialog.aquaduct_question",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "UI.dialogs.install_deps_dialog.install_dependencies_with_dialog",
        lambda _parent: (0, ""),
    )
    assert MainWindow._offer_runtime_install_for_preflight(w, pf) is True


@pytest.mark.qt
def test_preflight_failed_ui_triggers_install_offer(monkeypatch, qapplication):
    from UI.main_window import MainWindow

    w = MagicMock()
    w._last_preflight_dialog_key = ""
    w._last_preflight_dialog_t = 0.0
    pf = PreflightResult(
        ok=False,
        errors=["Missing Python packages: foo"],
        warnings=[],
    )
    calls: list[bool] = []

    def _offer(_pf):
        calls.append(True)
        return True

    w._offer_runtime_install_for_preflight = _offer
    assert MainWindow._preflight_failed_ui(w, pf) is True
    assert calls == [True]
