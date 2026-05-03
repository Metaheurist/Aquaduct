"""
Resolved Hugging Face model snapshot directory.

Default: ``<.Aquaduct_data>/models``. Optional **external** path from settings (large drive / shared cache).
"""

from __future__ import annotations

from pathlib import Path

from src.core.config import AppSettings, get_paths

_pipeline_models_dir: Path | None = None


def set_pipeline_models_dir(path: Path | None) -> None:
    """While running ``run_once`` (local inference), inference code uses this directory."""
    global _pipeline_models_dir
    _pipeline_models_dir = path.resolve() if path is not None else None


def clear_pipeline_models_dir() -> None:
    set_pipeline_models_dir(None)


def models_dir_for_app(app: AppSettings | None) -> Path:
    """
    Models directory for UI + downloads + loading weights.

    - ``default``: project ``.Aquaduct_data/models``.
    - ``external``: user-provided absolute folder (created if missing when valid).
    """
    base = get_paths().models_dir
    if app is None:
        return base
    mode = str(getattr(app, "models_storage_mode", "default") or "default").strip().lower()
    if mode != "external":
        return base
    raw = str(getattr(app, "models_external_path", "") or "").strip()
    if not raw:
        return base
    try:
        p = Path(raw).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError:
        return base


def get_models_dir() -> Path:
    """
    Directory for ``resolve_pretrained_load_path`` / diffusion loaders during a pipeline run.

    Uses the active pipeline override when set; otherwise default project models dir.
    """
    if _pipeline_models_dir is not None:
        return _pipeline_models_dir
    return get_paths().models_dir


def resolve_models_dir_for_pretrained(inference_settings: AppSettings | None = None) -> Path:
    """
    Root folder for resolving local HF snapshots (``resolve_pretrained_load_path``).

    Order: pipeline override (``run_once``) → explicit ``inference_settings`` → saved UI settings
    (so **external models path** matches the Model tab "on disk" badge when the pipeline
    override is unset, e.g. Characters / 🧠 expand before a run) → default ``get_paths().models_dir``.
    """
    if _pipeline_models_dir is not None:
        return _pipeline_models_dir
    if inference_settings is not None:
        return models_dir_for_app(inference_settings)
    try:
        from src.settings.ui_settings import load_settings

        return models_dir_for_app(load_settings())
    except Exception:
        return get_paths().models_dir
