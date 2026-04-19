from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import AppSettings
from src.speech.elevenlabs_tts import (
    effective_elevenlabs_api_key,
    elevenlabs_available_for_app,
    list_voices,
)


def test_effective_key_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "env_key")
    s = AppSettings(elevenlabs_api_key="saved")
    assert effective_elevenlabs_api_key(s) == "env_key"


def test_elevenlabs_available_requires_enabled_and_key() -> None:
    assert not elevenlabs_available_for_app(AppSettings())
    assert not elevenlabs_available_for_app(AppSettings(elevenlabs_enabled=True, elevenlabs_api_key=""))
    assert elevenlabs_available_for_app(AppSettings(elevenlabs_enabled=True, elevenlabs_api_key="x"))


@patch("src.speech.elevenlabs_tts.requests.get")
def test_list_voices_parses(mock_get: MagicMock) -> None:
    mock_get.return_value.json.return_value = {
        "voices": [
            {"voice_id": "v1", "name": "Alice"},
            {"voice_id": "v2", "name": "Bob"},
        ]
    }
    mock_get.return_value.raise_for_status = MagicMock()
    out = list_voices("k")
    assert ("Alice", "v1") in out
    assert ("Bob", "v2") in out


@patch("src.speech.elevenlabs_tts.synthesize_to_wav", return_value=True)
def test_voice_synthesize_calls_elevenlabs_first(mock_el: MagicMock, tmp_path: Path) -> None:
    pytest.importorskip("numpy")  # src.voice imports numpy
    from src.speech.voice import synthesize

    out_wav = tmp_path / "v.wav"
    caps = tmp_path / "c.json"
    ff = tmp_path / "ffmpeg.exe"
    ff.write_bytes(b"x")
    synthesize(
        kokoro_model_id="m",
        text="hello world",
        out_wav_path=out_wav,
        out_captions_json=caps,
        elevenlabs_voice_id="vid",
        elevenlabs_api_key="key",
        ffmpeg_executable=ff,
    )
    mock_el.assert_called_once()
    assert out_wav.exists()
    assert caps.exists()
