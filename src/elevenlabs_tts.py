from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import requests

from .config import AppSettings

BASE_URL = "https://api.elevenlabs.io/v1"


def effective_elevenlabs_api_key(settings: AppSettings) -> str:
    env = str(os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if env:
        return env
    return str(getattr(settings, "elevenlabs_api_key", "") or "").strip()


def elevenlabs_available_for_app(settings: AppSettings) -> bool:
    """Enabled in settings and a key is present (saved or env)."""
    if not bool(getattr(settings, "elevenlabs_enabled", False)):
        return False
    return bool(effective_elevenlabs_api_key(settings))


def list_voices(api_key: str, *, timeout: float = 45.0) -> list[tuple[str, str]]:
    """
    Returns sorted [(display_name, voice_id), ...].
    """
    if not (api_key or "").strip():
        return []
    r = requests.get(
        f"{BASE_URL}/voices",
        headers={"xi-api-key": api_key.strip()},
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    out: list[tuple[str, str]] = []
    for v in data.get("voices") or []:
        if not isinstance(v, dict):
            continue
        vid = str(v.get("voice_id") or "").strip()
        name = str(v.get("name") or vid).strip() or vid
        if vid:
            label = f"{name}"[:200]
            out.append((label, vid))
    out.sort(key=lambda x: x[0].lower())
    return out


def _tts_mp3(
    api_key: str,
    voice_id: str,
    text: str,
    *,
    model_id: str = "eleven_multilingual_v2",
    timeout: float = 120.0,
) -> bytes:
    url = f"{BASE_URL}/text-to-speech/{voice_id}"
    payload = {"text": text, "model_id": model_id}
    r = requests.post(
        url,
        json=payload,
        headers={
            "xi-api-key": api_key.strip(),
            "accept": "audio/mpeg",
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.content


def _mp3_bytes_to_wav(mp3_bytes: bytes, out_wav: Path, ffmpeg_bin: Path) -> bool:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
        tf.write(mp3_bytes)
        tmp_mp3 = Path(tf.name)
    try:
        cmd = [
            str(ffmpeg_bin),
            "-y",
            "-i",
            str(tmp_mp3),
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(out_wav),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return out_wav.exists() and out_wav.stat().st_size > 256
    except Exception:
        return False
    finally:
        try:
            tmp_mp3.unlink(missing_ok=True)
        except OSError:
            pass


def synthesize_to_wav(
    *,
    api_key: str,
    voice_id: str,
    text: str,
    out_wav: Path,
    ffmpeg_bin: Path,
) -> bool:
    """
    Generate speech via ElevenLabs, convert to mono PCM WAV for the rest of the pipeline.
    """
    try:
        mp3 = _tts_mp3(api_key.strip(), voice_id.strip(), text)
        return _mp3_bytes_to_wav(mp3, out_wav, ffmpeg_bin)
    except Exception:
        return False
