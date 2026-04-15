"""Project root resolution (repo root = parent of the `UI` package)."""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent
