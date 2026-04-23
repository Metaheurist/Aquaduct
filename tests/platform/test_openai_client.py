from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.core.config import ApiModelRuntimeSettings, ApiRoleConfig, AppSettings
from src.platform import openai_client as oc
from src.platform.openai_client import OpenAIClient, OpenAIRequestError


def test_chat_completion_parses_choice():
    client = OpenAIClient(api_key="k", base_url="https://api.openai.com/v1/")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": [{"message": {"content": '{"a":1}'}}]}
    with patch("src.platform.openai_client.requests.post", return_value=mock_resp) as post:
        out = client.chat_completion_text(model="gpt-4o-mini", system="s", user="u", json_mode=True)
    assert out == '{"a":1}'
    post.assert_called_once()


def test_chat_completion_retries_429_then_ok():
    client = OpenAIClient(api_key="k", base_url="https://api.openai.com/v1/")
    bad = MagicMock()
    bad.status_code = 429
    bad.text = "{}"
    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {"choices": [{"message": {"content": "done"}}]}
    with patch("src.platform.openai_client.requests.post", side_effect=[bad, ok]) as post:
        with patch("src.platform.openai_client._sleep_backoff"):
            out = client.chat_completion_text(model="gpt-4o-mini", system="s", user="u", json_mode=False)
    assert out == "done"
    assert post.call_count == 2


def test_map_http_error_429():
    msg = oc._map_http_error(429, "{}")
    assert "rate limited" in msg.lower()


def test_build_openai_client_default_base_for_groq(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    s = AppSettings(
        api_models=ApiModelRuntimeSettings(llm=ApiRoleConfig(provider="groq", model="llama-3.1-8b-instant"))
    )
    c = oc.build_openai_client_from_settings(s)
    assert "groq.com" in c.base_url


def test_build_client_gemini_base_no_double_v1(monkeypatch):
    """Gemini OpenAI-compatible root must not get an extra /v1 suffix."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    s = AppSettings(
        api_models=ApiModelRuntimeSettings(
            llm=ApiRoleConfig(provider="google_ai_studio", model="gemini-2.0-flash")
        )
    )
    c = oc.build_openai_client_from_settings(s)
    assert "generativelanguage.googleapis.com" in c.base_url
    assert "openai/v1/v1" not in c.base_url.replace("//", "/")
    assert c.base_url.rstrip("/").endswith("openai") or c.base_url.rstrip("/").endswith("openai/")


def test_build_client_requires_key():
    s = AppSettings(api_models=ApiModelRuntimeSettings(llm=ApiRoleConfig(provider="openai", model="gpt-4o-mini")))
    from src.platform import openai_client as oc
    from src.runtime import model_backend as mb

    with patch.object(mb, "effective_llm_api_key", return_value=""):
        try:
            oc.build_openai_client_from_settings(s)
        except OpenAIRequestError as e:
            assert "No API key" in str(e)
        else:
            raise AssertionError("expected OpenAIRequestError")
