from __future__ import annotations

import sys


def test_use_rich_cli_false_without_tty(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    from src.cli_pip_display import use_rich_cli

    assert use_rich_cli() is False


def test_use_rich_cli_false_with_plain_env(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setenv("AQUADUCT_PLAIN_CLI", "1")
    from src.cli_pip_display import use_rich_cli

    assert use_rich_cli() is False
