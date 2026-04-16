"""Mocked HTTP tests for TikTok OAuth token exchange (no real network)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def test_parse_token_response_success() -> None:
    from src.tiktok_post import parse_token_response

    out = parse_token_response(
        {
            "access_token": "act.x",
            "refresh_token": "rft.y",
            "open_id": "oid",
            "expires_in": 3600,
            "scope": "user.info.basic,video.upload",
        }
    )
    assert out["access_token"] == "act.x"
    assert out["refresh_token"] == "rft.y"


def test_parse_token_response_oauth_error() -> None:
    from src.tiktok_post import parse_token_response

    with pytest.raises(ValueError, match="bad"):
        parse_token_response({"error": "invalid_request", "error_description": "bad"})


def test_exchange_authorization_code_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import tiktok_post as tt

    fake = json.dumps(
        {
            "access_token": "act.ok",
            "refresh_token": "rft.ok",
            "open_id": "o1",
            "expires_in": 86400,
            "scope": "user.info.basic,video.upload",
        }
    ).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_resp
    mock_cm.__exit__.return_value = None

    with patch.object(tt.urllib.request, "urlopen", return_value=mock_cm):
        raw = tt.exchange_authorization_code(
            client_key="ck",
            client_secret="sec",
            code="cde",
            redirect_uri="http://127.0.0.1:8765/callback/",
            code_verifier="ver",
        )
    assert raw.get("access_token") == "act.ok"
