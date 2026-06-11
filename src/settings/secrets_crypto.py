"""Fernet encryption for secret fields in ui_settings.json."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from src.core.app_dirs import application_data_dir

_KEY_NAME = ".ui_settings_fernet.key"
_ENCRYPTED_PREFIX = "enc:"

SECRET_FIELDS: tuple[str, ...] = (
    "hf_token",
    "api_openai_key",
    "api_replicate_token",
    "firecrawl_api_key",
    "elevenlabs_api_key",
    "tiktok_client_secret",
    "tiktok_access_token",
    "tiktok_refresh_token",
    "youtube_client_secret",
    "youtube_access_token",
    "youtube_refresh_token",
)


def _key_path(data_dir: Path | None = None) -> Path:
    root = data_dir if data_dir is not None else application_data_dir()
    return root / _KEY_NAME


def _fernet_for_data_dir(data_dir: Path | None = None) -> Fernet:
    root = data_dir if data_dir is not None else application_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    key_file = _key_path(root)
    if key_file.exists():
        key = key_file.read_bytes().strip()
        if len(key) != 44:
            key = Fernet.generate_key()
            key_file.write_bytes(key)
    else:
        key = Fernet.generate_key()
        key_file.write_bytes(key)
    try:
        key_file.chmod(0o600)
    except Exception:
        pass
    return Fernet(key)


def _encrypt_value(fernet: Fernet, value: str) -> str:
    token = fernet.encrypt(value.encode("utf-8"))
    return _ENCRYPTED_PREFIX + token.decode("ascii")


def _decrypt_value(fernet: Fernet, stored: str) -> str:
    if not stored.startswith(_ENCRYPTED_PREFIX):
        return stored
    blob = stored[len(_ENCRYPTED_PREFIX) :]
    try:
        raw = fernet.decrypt(blob.encode("ascii"))
    except (InvalidToken, ValueError, OSError):
        return ""
    return raw.decode("utf-8")


def encrypt_settings_dict(data: dict[str, Any], *, data_dir: Path | None = None) -> dict[str, Any]:
    """Return a copy of ``data`` with known secret fields encrypted in place."""
    out = dict(data)
    fernet = _fernet_for_data_dir(data_dir)
    for field in SECRET_FIELDS:
        val = out.get(field)
        if not isinstance(val, str) or not val.strip():
            continue
        if val.startswith(_ENCRYPTED_PREFIX):
            continue
        out[field] = _encrypt_value(fernet, val)
    return out


def decrypt_settings_dict(data: dict[str, Any], *, data_dir: Path | None = None) -> dict[str, Any]:
    """Return a copy of ``data`` with encrypted secret fields decrypted."""
    out = dict(data)
    fernet = _fernet_for_data_dir(data_dir)
    for field in SECRET_FIELDS:
        val = out.get(field)
        if not isinstance(val, str) or not val:
            continue
        if val.startswith(_ENCRYPTED_PREFIX):
            out[field] = _decrypt_value(fernet, val)
    return out
