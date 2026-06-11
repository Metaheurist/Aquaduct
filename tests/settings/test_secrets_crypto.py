from __future__ import annotations

from src.settings.secrets_crypto import (
    SECRET_FIELDS,
    decrypt_settings_dict,
    encrypt_settings_dict,
)


def test_secrets_crypto_roundtrip(tmp_path, monkeypatch) -> None:
    from src.settings import secrets_crypto as mod

    monkeypatch.setattr(mod, "application_data_dir", lambda: tmp_path)
    raw = {
        "hf_token": "hf_secret",
        "api_openai_key": "sk-test",
        "personality_id": "auto",
    }
    enc = encrypt_settings_dict(raw, data_dir=tmp_path)
    assert enc["personality_id"] == "auto"
    assert enc["hf_token"].startswith("enc:")
    assert enc["api_openai_key"].startswith("enc:")
    dec = decrypt_settings_dict(enc, data_dir=tmp_path)
    assert dec["hf_token"] == "hf_secret"
    assert dec["api_openai_key"] == "sk-test"


def test_secrets_crypto_plaintext_migration(tmp_path, monkeypatch) -> None:
    from src.settings import secrets_crypto as mod

    monkeypatch.setattr(mod, "application_data_dir", lambda: tmp_path)
    raw = {field: f"plain_{field}" for field in SECRET_FIELDS[:3]}
    dec = decrypt_settings_dict(raw, data_dir=tmp_path)
    assert dec == raw
