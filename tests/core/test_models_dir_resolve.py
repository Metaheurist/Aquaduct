"""Coverage for ``resolve_models_dir_for_pretrained`` vs pipeline + external paths."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.core.config import AppSettings
from src.core import models_dir as md


def test_resolve_pipeline_override_wins_over_inference(monkeypatch) -> None:
    pipe = Path("/tmp/pipeline_models_only_test")
    monkeypatch.setattr(md, "_pipeline_models_dir", pipe)
    ext_app = replace(
        AppSettings(),
        models_storage_mode="external",
        models_external_path="D:\\external_models",
    )
    assert md.resolve_models_dir_for_pretrained(ext_app) == pipe
    monkeypatch.setattr(md, "_pipeline_models_dir", None)


def test_resolve_external_from_inference_settings(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(md, "_pipeline_models_dir", None)
    ext_root = tmp_path / "outside"
    st = replace(
        AppSettings(),
        models_storage_mode="external",
        models_external_path=str(ext_root),
    )
    resolved = md.resolve_models_dir_for_pretrained(st)
    assert resolved == ext_root.resolve()
    assert ext_root.is_dir()
