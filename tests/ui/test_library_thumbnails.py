from __future__ import annotations

from pathlib import Path

from UI.services.library_thumbnails import project_final_media, resolve_library_thumbnail


def test_project_final_media_paths(tmp_path: Path) -> None:
    assert project_final_media(tmp_path, photo=False).name == "final.mp4"
    assert project_final_media(tmp_path, photo=True).name == "final.png"


def test_resolve_library_thumbnail_photo_uses_final_png(tmp_path: Path) -> None:
    proj = tmp_path / "pic1"
    proj.mkdir()
    final = proj / "final.png"
    final.write_bytes(b"\x89PNG\r\n\x1a\n")
    out = resolve_library_thumbnail(proj, photo=True, ensure=False)
    assert out == final


def test_resolve_library_thumbnail_video_without_ffmpeg(tmp_path: Path) -> None:
    proj = tmp_path / "vid1"
    proj.mkdir()
    (proj / "final.mp4").write_bytes(b"\x00" * 512)
    out = resolve_library_thumbnail(proj, photo=False, ffmpeg_dir=None, ensure=False)
    assert out is None
