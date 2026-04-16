from __future__ import annotations

from pathlib import Path


def test_project_dirname_roundtrip():
    from src.model_manager import project_dirname_to_repo_id, project_model_dirname

    rid = "hexgrad/Kokoro-82M"
    dname = project_model_dirname(rid)
    assert "__" in dname
    back = project_dirname_to_repo_id(dname)
    assert back == rid


def test_verify_skips_empty_or_missing(tmp_path):
    from src import model_manager as mm

    r = mm.verify_project_model_integrity("", models_dir=tmp_path)
    assert not r.ok
    assert "empty" in r.error.lower()

    r2 = mm.verify_project_model_integrity("some/org", models_dir=tmp_path)
    assert not r2.ok
    assert "not installed" in r2.error.lower()


def test_integrity_classify_and_worst():
    from src.model_integrity_cache import classify_integrity_status, merge_integrity_cache, worst_integrity_status
    from src.model_manager import ModelIntegrityReport

    assert classify_integrity_status(ModelIntegrityReport(repo_id="a/b", ok=True)) == "ok"
    assert classify_integrity_status(ModelIntegrityReport(repo_id="a/b", ok=False, error="x")) == "error"
    assert classify_integrity_status(ModelIntegrityReport(repo_id="a/b", ok=False, missing_paths=["a"])) == "missing"
    assert classify_integrity_status(ModelIntegrityReport(repo_id="a/b", ok=False, mismatches=[{"path": "w"}])) == "corrupt"
    assert (
        classify_integrity_status(
            ModelIntegrityReport(repo_id="a/b", ok=False, missing_paths=["a"], mismatches=[{"path": "w"}])
        )
        == "missing_and_corrupt"
    )

    assert worst_integrity_status(["missing", "corrupt"]) == "corrupt"
    assert worst_integrity_status(["ok", "missing"]) == "missing"

    m = merge_integrity_cache({"x": "ok"}, {"y": "missing"})
    assert m["x"] == "ok" and m["y"] == "missing"


def test_list_installed_repo_ids_from_disk(tmp_path, monkeypatch):
    from src import model_manager as mm

    monkeypatch.setattr(mm, "min_bytes_for_snapshot", lambda: 10)
    (tmp_path / "a__b").mkdir(parents=True)
    tiny = tmp_path / "a__b" / "x.txt"
    tiny.write_text("12345678901")  # 11 bytes >= 10

    ids = mm.list_installed_repo_ids_from_disk(tmp_path)
    assert "a/b" in ids
