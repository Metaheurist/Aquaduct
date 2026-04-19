from __future__ import annotations

import json
from pathlib import Path

from UI.library_fs import format_byte_size, scan_finished_videos, scan_run_workspaces


def test_format_byte_size() -> None:
    assert format_byte_size(0) == "0 B"
    assert format_byte_size(500) == "500 B"
    assert "KB" in format_byte_size(2048)


def test_scan_finished_videos(tmp_path: Path) -> None:
    v = tmp_path / "videos"
    v.mkdir()
    incomplete = v / "no_final"
    incomplete.mkdir()
    (incomplete / "meta.json").write_text(json.dumps({"title": "Skip"}), encoding="utf-8")

    done = v / "My_Video_Project"
    done.mkdir()
    (done / "meta.json").write_text(json.dumps({"title": "Hello Title"}), encoding="utf-8")
    (done / "final.mp4").write_bytes(b"x" * 8000)

    rows = scan_finished_videos(v)
    assert len(rows) == 1
    assert rows[0].folder_name == "My_Video_Project"
    assert rows[0].title == "Hello Title"
    assert rows[0].final_bytes == 8000
    assert rows[0].path == done.resolve()


def test_scan_run_workspaces(tmp_path: Path) -> None:
    r = tmp_path / "runs"
    r.mkdir()
    a = r / "run-a"
    a.mkdir()
    (a / "assets").mkdir()
    b = r / "run-b"
    b.mkdir()

    rows = scan_run_workspaces(r)
    names = {x.path.name for x in rows}
    assert names == {"run-a", "run-b"}
    by_name = {x.path.name: x for x in rows}
    assert by_name["run-a"].has_assets_dir is True
    assert by_name["run-b"].has_assets_dir is False


def test_scan_missing_dirs(tmp_path: Path) -> None:
    assert scan_finished_videos(tmp_path / "nope") == []
    assert scan_run_workspaces(tmp_path / "missing") == []
