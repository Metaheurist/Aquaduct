from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from pathlib import Path

import requests

from src.core.config import AppSettings

TTS_URL = "https://api.inworld.ai/tts/v1/voice"
_MAX_CHUNK = 1900


def effective_inworld_api_key(settings: AppSettings | None) -> str:
    v = (os.environ.get("INWORLD_API_KEY") or "").strip()
    if v:
        return v
    if settings is None:
        return ""
    return str(getattr(settings, "api_openai_key", "") or "").strip()


def _chunk_text(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    if len(t) <= _MAX_CHUNK:
        return [t]
    parts: list[str] = []
    start = 0
    while start < len(t):
        end = min(len(t), start + _MAX_CHUNK)
        if end < len(t):
            cut = t.rfind(". ", start, end)
            if cut <= start:
                cut = t.rfind(" ", start, end)
            if cut > start:
                end = cut + 1
        chunk = t[start:end].strip()
        if chunk:
            parts.append(chunk)
        start = end
    return parts or [t[:_MAX_CHUNK]]


def _inworld_tts_bytes(*, api_key: str, text: str, model_id: str, voice_id: str, timeout: float = 120.0) -> bytes:
    r = requests.post(
        TTS_URL,
        headers={
            "Authorization": f"Basic {api_key.strip()}",
            "Content-Type": "application/json",
        },
        json={"text": text, "voiceId": voice_id or "Sarah", "modelId": (model_id or "inworld-tts-1.5-max").strip()},
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    b64 = data.get("audioContent")
    if not b64:
        raise RuntimeError("Inworld TTS response missing audioContent.")
    return base64.b64decode(str(b64))


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


def _concat_wavs(ffmpeg_bin: Path, parts: list[Path], out_wav: Path) -> bool:
    if not parts:
        return False
    if len(parts) == 1:
        try:
            out_wav.write_bytes(parts[0].read_bytes())
            return True
        except OSError:
            return False
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as cf:
        for p in parts:
            cf.write(f"file '{p.as_posix()}'\n")
        list_path = Path(cf.name)
    try:
        cmd = [str(ffmpeg_bin), "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_wav)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return out_wav.exists() and out_wav.stat().st_size > 256
    except Exception:
        return False
    finally:
        try:
            list_path.unlink(missing_ok=True)
        except OSError:
            pass


def synthesize_inworld_to_wav(
    *,
    settings: AppSettings,
    text: str,
    model_id: str,
    voice_id: str,
    out_wav: Path,
    ffmpeg_bin: Path,
) -> bool:
    key = effective_inworld_api_key(settings)
    if not key:
        return False
    chunks = _chunk_text(text)
    if not chunks:
        return False
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        wavs: list[Path] = []
        for i, ch in enumerate(chunks):
            mp3 = _inworld_tts_bytes(api_key=key, text=ch, model_id=model_id, voice_id=voice_id)
            part_wav = tdir / f"part_{i:03d}.wav"
            if not _mp3_bytes_to_wav(mp3, part_wav, ffmpeg_bin):
                return False
            wavs.append(part_wav)
        return _concat_wavs(ffmpeg_bin, wavs, out_wav)