"""Merge partial settings dicts into AppSettings (CLI ``--merge-json``)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.core.config import AppSettings
from src.settings.ui_settings import app_settings_from_dict


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for k, v in over.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def merge_partial_app_settings(base: AppSettings, partial: dict[str, Any]) -> AppSettings:
    """
    Deep-merge ``partial`` onto ``asdict(base)``, then parse with the same rules as ``ui_settings.json``.

    Unknown keys in ``partial`` are merged at the dict level; ``app_settings_from_dict`` only reads
    known fields when constructing dataclasses.
    """
    merged = _deep_merge(asdict(base), partial)
    return app_settings_from_dict(merged)
