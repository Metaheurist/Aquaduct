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
        E("401 Client Error: you are trying to access a gated repo for meta-llama/Meta-Llama-3.1-8B-Instruct")
    )
    assert msg is not None
    assert "gated" in msg.lower() or "401" in msg
    assert "huggingface" in msg.lower()
