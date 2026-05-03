import os

from src.models.hf_access import ensure_hf_token_in_env, humanize_hf_hub_error


def test_ensure_hf_token_applies_even_when_hf_api_toggle_off(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACEHUB_API_TOKEN", raising=False)
    ensure_hf_token_in_env(hf_token="test-hf-token", hf_api_enabled=False)
    assert os.environ.get("HF_TOKEN") == "test-hf-token"


def test_humanize_gated_repo_error():
    class E(Exception):
        pass

    msg = humanize_hf_hub_error(
        E("401 Client Error: you are trying to access a gated repo for sophosympatheia/Midnight-Miqu-70B-v1.5")
    )
    assert msg is not None
    assert "gated" in msg.lower() or "401" in msg
    assert "huggingface" in msg.lower()


def test_humanize_not_json_errors_with_stray_401_in_text():
    """LLM error previews can mention 401(k) etc.; must not map to Hub download copy."""
    exc = ValueError(
        'Model did not return a JSON object. Preview: {"notes": {"x": "Discuss 401(k) rollovers"}}'
    )
    assert humanize_hf_hub_error(exc) is None
