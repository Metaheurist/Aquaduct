"""SSRF guard for user-influenced outbound HTTP(S) URLs."""

from __future__ import annotations

import pytest

from src.util.ssrf_guard import is_safe_http_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/article",
        "http://news.ycombinator.com/item",
    ],
)
def test_safe_public_urls(url: str) -> None:
    assert is_safe_http_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.com/x",
        "file:///etc/passwd",
        "http://127.0.0.1/admin",
        "http://localhost/secret",
        "https://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal",
        "http://[::1]/",
    ],
)
def test_blocked_urls(url: str) -> None:
    assert is_safe_http_url(url) is False
