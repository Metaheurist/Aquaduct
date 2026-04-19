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


def test_build_client_requires_key():
    s = AppSettings(api_models=ApiModelRuntimeSettings(llm=ApiRoleConfig(provider="openai", model="gpt-4o-mini")))
    from src.platform import openai_client as oc
    from src.runtime import model_backend as mb

    with patch.object(mb, "effective_openai_api_key", return_value=""):
        try:
            oc.build_openai_client_from_settings(s)
        except OpenAIRequestError as e:
            assert "No OpenAI API key" in str(e)
        else:
            raise AssertionError("expected OpenAIRequestError")
