"""Outbound HTTP helpers must refuse non-HTTPS URLs before calling urlopen."""

from __future__ import annotations

import pytest

from src.platform import tiktok_post


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/win.ini",
        "http://open.tiktokapis.com/v2/oauth/token/",
        "ftp://example.com/upload",
        "",
    ],
)
def test_tiktok_helpers_reject_non_https(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_network(*_a, **_k):
        raise AssertionError("urlopen must not be reached for a rejected URL")

    monkeypatch.setattr(tiktok_post.urllib.request, "urlopen", _no_network)

    with pytest.raises(ValueError, match="non-HTTPS"):
        tiktok_post._form_post(url, {"a": "b"})
    with pytest.raises(ValueError, match="non-HTTPS"):
        tiktok_post._json_post_authed(url, "token", {})
    with pytest.raises(ValueError, match="non-HTTPS"):
        tiktok_post._put_video_chunk(url, b"x", "video/mp4", 0, 0, 1)


def test_tiktok_api_constants_are_https() -> None:
    for url in (tiktok_post.TOKEN_URL, tiktok_post.AUTH_URL, tiktok_post.INBOX_INIT_URL):
        assert url.startswith("https://")
