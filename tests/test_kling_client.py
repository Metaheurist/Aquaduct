from __future__ import annotations

from src.platform import kling_client as kc


def test_kling_jwt_three_parts() -> None:
    t = kc.kling_bearer_jwt("access_key_test", "secret_key_test", lifetime_s=600)
    parts = t.split(".")
    assert len(parts) == 3
    assert all(len(p) > 4 for p in parts)


def test_extract_video_url_nested() -> None:
    u = kc._extract_video_url(  # type: ignore[attr-defined]
        {"x": {"task_result": {"videos": [{"url": "https://cdn.example.com/a.mp4"}]}}}
    )
    assert u == "https://cdn.example.com/a.mp4"
