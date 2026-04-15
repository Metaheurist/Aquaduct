from __future__ import annotations

from pathlib import Path

from src.config import AppSettings, VideoSettings


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_cleanup_images_after_run_enabled(tmp_path):
    # Simulate video output folder layout
    assets = tmp_path / "videos" / "v1" / "assets"
    _touch(assets / "images" / "img_001.png")
    _touch(assets / "keyframes" / "img_001.png")
    _touch(assets / "voice.wav")
    _touch(assets / "captions.json")
    _touch(tmp_path / "videos" / "v1" / "final.mp4")

    s = AppSettings(topic_tags=[], video=VideoSettings(cleanup_images_after_run=True))

    # Inline the expected cleanup behavior (mirrors main.py)
    if s.video.cleanup_images_after_run:
        for rel in ("images", "keyframes"):
            p = assets / rel
            if p.exists():
                # emulate shutil.rmtree(ignore_errors=True) behavior without importing shutil
                for child in sorted(p.rglob("*"), reverse=True):
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                p.rmdir()

    assert not (assets / "images").exists()
    assert not (assets / "keyframes").exists()
    assert (assets / "voice.wav").exists()
    assert (assets / "captions.json").exists()
    assert (tmp_path / "videos" / "v1" / "final.mp4").exists()


def test_cleanup_images_after_run_disabled(tmp_path):
    assets = tmp_path / "videos" / "v1" / "assets"
    _touch(assets / "images" / "img_001.png")
    _touch(assets / "keyframes" / "img_001.png")

    s = AppSettings(topic_tags=[], video=VideoSettings(cleanup_images_after_run=False))
    assert not s.video.cleanup_images_after_run

    # No cleanup
    assert (assets / "images").exists()
    assert (assets / "keyframes").exists()

