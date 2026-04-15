from __future__ import annotations

from pathlib import Path

from src.model_manager import download_model_to_project, model_options


def test_model_options_enumerated_and_sorted():
    opts = model_options()
    assert opts
    # orders should restart per kind starting at 1
    kinds = {}
    for o in opts:
        kinds.setdefault(o.kind, []).append(o.order)
    for k, orders in kinds.items():
        assert orders[0] == 1
        assert orders == sorted(orders)


def test_download_model_to_project_calls_snapshot_download(tmp_path, monkeypatch):
    calls = {}

    def fake_snapshot_download(**kwargs):
        calls.update(kwargs)
        return str(tmp_path / "out")

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_snapshot_download, raising=False)
    out = download_model_to_project("repo/id", models_dir=tmp_path)
    assert isinstance(out, Path)
    assert calls["repo_id"] == "repo/id"
    assert "local_dir" in calls

