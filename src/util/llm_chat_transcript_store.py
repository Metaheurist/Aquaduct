"""Encrypted JSON persistence for LLM chat transcripts (Fernet)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

_KEY_NAME = ".llm_chat_fernet.key"


def _key_path(data_dir: Path) -> Path:
    return data_dir / _KEY_NAME


def _fernet_for_data_dir(data_dir: Path) -> Fernet:
    data_dir.mkdir(parents=True, exist_ok=True)
    key_file = _key_path(data_dir)
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


def safe_slug(s: str, *, max_len: int = 80) -> str:
    raw = re.sub(r"[^a-zA-Z0-9._-]+", "_", (s or "").strip())[:max_len].strip("_")
    return raw or "default"


def transcript_blob_path(data_dir: Path, *, mode: str, model_key: str) -> Path:
    chat_dir = data_dir / "chat"
    chat_dir.mkdir(parents=True, exist_ok=True)
    slug = safe_slug(f"{mode}_{model_key}")
    return chat_dir / f"llm_chat_{slug}.enc"


def load_transcript(
    data_dir: Path,
    *,
    mode: str,
    model_key: str,
) -> dict[str, Any] | None:
    path = transcript_blob_path(data_dir, mode=mode, model_key=model_key)
    if not path.is_file():
        return None
    try:
        f = _fernet_for_data_dir(data_dir)
        raw = f.decrypt(path.read_bytes())
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (InvalidToken, json.JSONDecodeError, OSError, ValueError):
        return None


def save_transcript(
    data_dir: Path,
    *,
    mode: str,
    model_key: str,
    messages: list[dict[str, Any]],
    system_prompt: str,
    max_messages: int = 200,
) -> None:
    path = transcript_blob_path(data_dir, mode=mode, model_key=model_key)
    msgs = messages[-max_messages:]
    payload = {
        "messages": msgs,
        "system_prompt": system_prompt,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    fer = _fernet_for_data_dir(data_dir)
    token = fer.encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(token)
    try:
        path.chmod(0o600)
    except Exception:
        pass


def delete_transcript(data_dir: Path, *, mode: str, model_key: str) -> None:
    path = transcript_blob_path(data_dir, mode=mode, model_key=model_key)
    try:
        path.unlink(missing_ok=True)  # type: ignore[arg-type]
    except TypeError:
        if path.is_file():
            path.unlink()
