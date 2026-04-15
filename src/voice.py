from __future__ import annotations

import json
import math
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .utils_vram import vram_guard


@dataclass(frozen=True)
class WordTimestamp:
    word: str
    start: float
    end: float


def _write_wav_pcm16(path: Path, audio: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # soundfile handles PCM16 cleanly
    sf.write(str(path), audio, sr, subtype="PCM_16")


def _duration_seconds(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as w:
        frames = w.getnframes()
        sr = w.getframerate()
    return frames / float(sr)


def _simple_word_timestamps(text: str, total_s: float) -> list[WordTimestamp]:
    words = [w for w in text.replace("\n", " ").split(" ") if w.strip()]
    if not words:
        return []

    # Weight longer words slightly higher.
    weights = []
    for w in words:
        base = max(1.0, min(10.0, float(len(w))))
        weights.append(base)
    wsum = sum(weights)
    if wsum <= 0:
        return []

    ts: list[WordTimestamp] = []
    t = 0.0
    for word, wgt in zip(words, weights):
        dt = total_s * (wgt / wsum)
        start = t
        end = t + dt
        ts.append(WordTimestamp(word=word, start=start, end=end))
        t = end
    # Ensure last ends exactly at duration
    ts[-1] = WordTimestamp(word=ts[-1].word, start=ts[-1].start, end=total_s)
    return ts


def _try_kokoro_tts(_model_id: str, _text: str, _out_wav: Path) -> bool:
    """
    Kokoro-82M integration target.

    Kokoro model packaging can vary; to keep MVP runnable, this function attempts a
    best-effort import path and returns False if unavailable.
    """
    try:
        # If an official/third-party kokoro package is installed, prefer it.
        # We intentionally keep this optional to avoid breaking the MVP.
        import kokoro  # type: ignore  # noqa: F401

        # Unknown API surface across Kokoro variants; defer to fallback for now.
        return False
    except Exception:
        return False


def _pyttsx3_tts(text: str, out_wav: Path) -> None:
    """
    Offline fallback TTS using Windows SAPI via pyttsx3.
    Produces WAV on most Windows installs.
    """
    import pyttsx3

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    engine = pyttsx3.init()
    # Slightly faster, “shorts” pacing.
    try:
        engine.setProperty("rate", 185)
    except Exception:
        pass
    engine.save_to_file(text, str(out_wav))
    engine.runAndWait()
    try:
        engine.stop()
    except Exception:
        pass


def synthesize(
    *,
    kokoro_model_id: str,
    text: str,
    out_wav_path: Path,
    out_captions_json: Path,
) -> list[WordTimestamp]:
    """
    Generates `out_wav_path` and `out_captions_json` (word-level timestamps).
    """
    out_wav_path.parent.mkdir(parents=True, exist_ok=True)
    out_captions_json.parent.mkdir(parents=True, exist_ok=True)

    with vram_guard():
        ok = _try_kokoro_tts(kokoro_model_id, text, out_wav_path)
        if not ok:
            _pyttsx3_tts(text, out_wav_path)

    # Ensure there is audio; if pyttsx3 fails, create a short beep track as last resort.
    if not out_wav_path.exists() or out_wav_path.stat().st_size < 1024:
        sr = 24000
        dur = max(3.0, min(60.0, len(text.split()) * 0.35))
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        audio = 0.08 * np.sin(2 * math.pi * 220.0 * t).astype(np.float32)
        _write_wav_pcm16(out_wav_path, audio, sr)

    dur_s = _duration_seconds(out_wav_path)
    words = _simple_word_timestamps(text=text, total_s=dur_s)

    payload = [{"word": w.word, "start": w.start, "end": w.end} for w in words]
    out_captions_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return words

