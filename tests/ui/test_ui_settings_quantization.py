"""
Persistence tests for the per-model quantization settings.
"""
from __future__ import annotations

import json

from src.core.config import AppSettings
from src.settings.ui_settings import app_settings_from_dict, load_settings, save_settings


def test_save_roundtrip_quant_modes(tmp_path, monkeypatch) -> None:
    from src.settings import ui_settings as us

    p = tmp_path / "ui_settings.json"
    monkeypatch.setattr(us, "settings_path", lambda: p)

    s = AppSettings(
        script_quant_mode="nf4_4bit",  # type: ignore[arg-type]
        image_quant_mode="bf16",  # type: ignore[arg-type]
        video_quant_mode="cpu_offload",  # type: ignore[arg-type]
        voice_quant_mode="fp16",  # type: ignore[arg-type]
    )
    assert save_settings(s) is True

    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw.get("script_quant_mode") == "nf4_4bit"
    assert raw.get("image_quant_mode") == "bf16"
    assert raw.get("video_quant_mode") == "cpu_offload"
    assert raw.get("voice_quant_mode") == "fp16"

    loaded = load_settings()
    assert loaded.script_quant_mode == "nf4_4bit"
    assert loaded.image_quant_mode == "bf16"
    assert loaded.video_quant_mode == "cpu_offload"
    assert loaded.voice_quant_mode == "fp16"


def test_legacy_try_llm_4bit_migrates_to_script_quant_mode() -> None:
    """When ``script_quant_mode`` is absent, fall back to ``try_llm_4bit`` for migration."""
    s_true = app_settings_from_dict({"try_llm_4bit": True})
    assert s_true.script_quant_mode == "nf4_4bit"

    s_false = app_settings_from_dict({"try_llm_4bit": False})
    assert s_false.script_quant_mode == "fp16"

    # Explicit script_quant_mode wins over the legacy bool.
    s_override = app_settings_from_dict({"try_llm_4bit": False, "script_quant_mode": "int8"})
    assert s_override.script_quant_mode == "int8"


def test_load_tolerates_unknown_quant_mode_strings() -> None:
    s = app_settings_from_dict({"image_quant_mode": "garbage"})
    assert s.image_quant_mode == "auto"


def test_alias_strings_normalize_via_loader() -> None:
    s = app_settings_from_dict(
        {
            "script_quant_mode": "4bit",
            "image_quant_mode": "8bit",
            "video_quant_mode": "cpu",
            "voice_quant_mode": "auto",
        }
    )
    assert s.script_quant_mode == "nf4_4bit"
    assert s.image_quant_mode == "int8"
    assert s.video_quant_mode == "cpu_offload"
    assert s.voice_quant_mode == "auto"
