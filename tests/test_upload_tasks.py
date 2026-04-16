from __future__ import annotations

import json

import pytest


def test_append_task_dedupes_by_folder(tmp_path, monkeypatch):
    from src import upload_tasks as ut_mod

    monkeypatch.setattr(ut_mod, "upload_tasks_path", lambda: tmp_path / "upload_tasks.json")

    d = tmp_path / "videos" / "My_Video"
    d.mkdir(parents=True)
    (d / "final.mp4").write_bytes(b"x")

    t1 = ut_mod.append_task_for_video_dir(d)
    t2 = ut_mod.append_task_for_video_dir(d)
    assert t1 is not None
    assert t2 is None
    tasks = ut_mod.load_tasks()
    assert len(tasks) == 1


def test_load_save_roundtrip(tmp_path, monkeypatch):
    from src import upload_tasks as ut_mod

    monkeypatch.setattr(ut_mod, "upload_tasks_path", lambda: tmp_path / "upload_tasks.json")

    d = tmp_path / "v"
    d.mkdir(parents=True)
    (d / "final.mp4").write_bytes(b"x")
    ut_mod.append_task_for_video_dir(d)
    p = tmp_path / "upload_tasks.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 1

    t2 = ut_mod.load_tasks()
    assert len(t2) == 1
    assert t2[0].status == "pending"
