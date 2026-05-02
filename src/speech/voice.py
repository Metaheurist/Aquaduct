from __future__ import annotations

import json
import math
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from src.speech.tts_kokoro_moss import (
    DEFAULT_MOSS_INSTRUCTION,
    is_kokoro_repo,
    is_moss_vg_repo,
    is_pyttsx3_fallback_repo,
    kokoro_speaker_for_unhinged_segment,
    pick_kokoro_speaker,
    try_kokoro_tts,
    try_moss_voicegenerator_tts,
)
from src.util.utils_vram import vram_guard


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


def list_pyttsx3_voices() -> list[tuple[str, str]]:
    """Return [(label, voice_id), ...] for installed system TTS voices (pyttsx3)."""
    try:
        import pyttsx3

        engine = pyttsx3.init()
        out: list[tuple[str, str]] = []
        for v in engine.getProperty("voices") or []:
            vid = str(getattr(v, "id", "") or "")
            if not vid:
                continue
            name = str(getattr(v, "name", "") or vid)
            out.append((name, vid))
        try:
            engine.stop()
        except Exception:
            pass
        return out
    except Exception:
        return []


UNHINGED_ROTATION_MAX_VOICES = 12


def _synthesize_tts_to_wav(
    *,
    kokoro_model_id: str,
    text: str,
    out_wav_path: Path,
    pyttsx3_voice_id: str | None = None,
    kokoro_speaker: str | None = None,
    voice_instruction: str | None = None,
    elevenlabs_voice_id: str | None = None,
    elevenlabs_api_key: str | None = None,
    ffmpeg_executable: Path | None = None,
    only_pyttsx3: bool = False,
    voice_quant_mode: str | None = None,
    voice_cuda_device_index: int | None = None,
) -> None:
    """
    Write speech-only WAV using the same backend order as ``synthesize`` (ElevenLabs → Kokoro → pyttsx3).
    Does not write captions. May synthesize a short beep if output is missing/empty.

    ``only_pyttsx3`` skips cloud/Kokoro (for per-segment local voice rotation).
    """
    out_wav_path.parent.mkdir(parents=True, exist_ok=True)
    if only_pyttsx3 or is_pyttsx3_fallback_repo(kokoro_model_id):
        with vram_guard():
            _pyttsx3_tts(text, out_wav_path, pyttsx3_voice_id=pyttsx3_voice_id)
    else:
        with vram_guard():
            el_ok = False
            ev = (elevenlabs_voice_id or "").strip()
            ek = (elevenlabs_api_key or "").strip()
            if ev and ek and ffmpeg_executable is not None:
                try:
                    from src.speech.elevenlabs_tts import synthesize_to_wav

                    el_ok = synthesize_to_wav(
                        api_key=ek,
                        voice_id=ev,
                        text=text,
                        out_wav=out_wav_path,
                        ffmpeg_bin=ffmpeg_executable,
                    )
                except Exception:
                    el_ok = False
            if not el_ok:
                vid = (kokoro_model_id or "").strip()
                if is_pyttsx3_fallback_repo(vid):
                    _pyttsx3_tts(text, out_wav_path, pyttsx3_voice_id=pyttsx3_voice_id)
                elif is_moss_vg_repo(vid):
                    inst = (voice_instruction or "").strip() or DEFAULT_MOSS_INSTRUCTION
                    if not try_moss_voicegenerator_tts(
                        model_id=vid,
                        text=text,
                        instruction=inst,
                        out_wav=out_wav_path,
                        quant_mode=voice_quant_mode,
                        cuda_voice_device_index=voice_cuda_device_index,
                    ):
                        _pyttsx3_tts(text, out_wav_path, pyttsx3_voice_id=pyttsx3_voice_id)
                elif is_kokoro_repo(vid):
                    sp = pick_kokoro_speaker(kokoro_speaker)
                    if not try_kokoro_tts(
                        model_id=vid,
                        text=text,
                        out_wav=out_wav_path,
                        speaker=sp,
                        quant_mode=voice_quant_mode,
                    ):
                        _pyttsx3_tts(text, out_wav_path, pyttsx3_voice_id=pyttsx3_voice_id)
                else:
                    _pyttsx3_tts(text, out_wav_path, pyttsx3_voice_id=pyttsx3_voice_id)

    if not out_wav_path.exists() or out_wav_path.stat().st_size < 1024:
        sr = 24000
        dur = max(3.0, min(60.0, len(text.split()) * 0.35))
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        audio = 0.08 * np.sin(2 * math.pi * 220.0 * t).astype(np.float32)
        _write_wav_pcm16(out_wav_path, audio, sr)


def _pyttsx3_tts(text: str, out_wav: Path, pyttsx3_voice_id: str | None = None) -> None:
    """
    Offline fallback TTS using Windows SAPI via pyttsx3.
    Produces WAV on most Windows installs.
    """
    import pyttsx3

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    engine = pyttsx3.init()
    if pyttsx3_voice_id and str(pyttsx3_voice_id).strip():
        vid = str(pyttsx3_voice_id).strip()
        try:
            for v in engine.getProperty("voices") or []:
                if str(getattr(v, "id", "") or "") == vid:
                    engine.setProperty("voice", v.id)
                    break
        except Exception:
            pass
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
    pyttsx3_voice_id: str | None = None,
    kokoro_speaker: str | None = None,
    voice_instruction: str | None = None,
    elevenlabs_voice_id: str | None = None,
    elevenlabs_api_key: str | None = None,
    ffmpeg_executable: Path | None = None,
    voice_quant_mode: str | None = None,
    voice_cuda_device_index: int | None = None,
) -> list[WordTimestamp]:
    """
    Generates `out_wav_path` and `out_captions_json` (word-level timestamps).
    """
    from debug import dprint

    dprint("voice", "synthesize", f"model={kokoro_model_id!r}", f"chars={len(text)}")
    out_captions_json.parent.mkdir(parents=True, exist_ok=True)

    _synthesize_tts_to_wav(
        kokoro_model_id=kokoro_model_id,
        text=text,
        out_wav_path=out_wav_path,
        pyttsx3_voice_id=pyttsx3_voice_id,
        kokoro_speaker=kokoro_speaker,
        voice_instruction=voice_instruction,
        elevenlabs_voice_id=elevenlabs_voice_id,
        elevenlabs_api_key=elevenlabs_api_key,
        ffmpeg_executable=ffmpeg_executable,
        only_pyttsx3=False,
        voice_quant_mode=voice_quant_mode,
        voice_cuda_device_index=voice_cuda_device_index,
    )

    dur_s = _duration_seconds(out_wav_path)
    words = _simple_word_timestamps(text=text, total_s=dur_s)

    payload = [{"word": w.word, "start": w.start, "end": w.end} for w in words]
    out_captions_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    dprint("voice", "synthesize done", f"word_timestamps={len(words)}")
    return words


def _read_wav_mono_i16(path: Path) -> tuple[np.ndarray, int]:
    """PCM int16 mono + sample rate."""
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if data.ndim == 2 and data.shape[1] > 1:
        mono = np.mean(data.astype(np.float64), axis=1)
    else:
        mono = data[:, 0].astype(np.float64) if data.ndim == 2 else data.astype(np.float64)
    i16 = (np.clip(mono, -1.0, 1.0) * 32767.0).astype(np.int16)
    return i16, int(sr)


def _resample_linear_i16(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or len(x) == 0:
        return x
    n_in = len(x)
    n_out = max(1, int(round(n_in * sr_out / float(sr_in))))
    t_in = np.linspace(0.0, float(n_in - 1), num=n_in)
    t_out = np.linspace(0.0, float(n_in - 1), num=n_out)
    xf = x.astype(np.float64) / 32767.0
    y = np.interp(t_out, t_in, xf)
    return (np.clip(y, -1.0, 1.0) * 32767.0).astype(np.int16)


def concat_pcm16_wavs(paths: list[Path], out_path: Path) -> None:
    """Concatenate mono PCM WAVs; resample to the first file's sample rate."""
    if not paths:
        raise ValueError("concat_pcm16_wavs: empty paths")
    chunks: list[np.ndarray] = []
    target_sr: int | None = None
    for p in paths:
        data, sr = _read_wav_mono_i16(p)
        if target_sr is None:
            target_sr = sr
        elif sr != target_sr:
            data = _resample_linear_i16(data, sr, target_sr)
        chunks.append(data)
    merged = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    audio_f = merged.astype(np.float32) / 32767.0
    sf.write(str(out_path), audio_f, int(target_sr or 24000), subtype="PCM_16")


def synthesize_unhinged_rotating_pyttsx3(
    *,
    kokoro_model_id: str,
    segment_texts: list[str],
    out_wav_path: Path,
    out_captions_json: Path,
) -> list[WordTimestamp]:
    """
    One local pyttsx3 voice per non-empty segment (round-robin, max
    ``UNHINGED_ROTATION_MAX_VOICES`` distinct voices). Concatenates WAVs and merges
    word timestamps. Does not use ElevenLabs or Kokoro (call sites must bypass
    when cloud TTS is active).
    """
    from debug import dprint

    dprint("voice", "synthesize_unhinged", f"segments={len(segment_texts)}")
    out_captions_json.parent.mkdir(parents=True, exist_ok=True)
    raw_ids = [vid for _, vid in list_pyttsx3_voices()][:UNHINGED_ROTATION_MAX_VOICES]
    voice_ids: list[str | None] = [v for v in raw_ids if (v or "").strip()] if raw_ids else []
    if not voice_ids:
        voice_ids = [None]

    offset_s = 0.0
    combined: list[WordTimestamp] = []
    temp_paths: list[Path] = []
    v_idx = 0
    try:
        for text in segment_texts:
            t = (text or "").strip()
            if not t:
                continue
            py_vid = voice_ids[v_idx % len(voice_ids)]
            v_idx += 1
            tmp = out_wav_path.parent / f"_unhinged_seg_{len(temp_paths):03d}.wav"
            _synthesize_tts_to_wav(
                kokoro_model_id=kokoro_model_id,
                text=t,
                out_wav_path=tmp,
                pyttsx3_voice_id=py_vid,
                kokoro_speaker=None,
                voice_instruction=None,
                elevenlabs_voice_id=None,
                elevenlabs_api_key=None,
                ffmpeg_executable=None,
                only_pyttsx3=True,
            )
            dur = _duration_seconds(tmp)
            for w in _simple_word_timestamps(text=t, total_s=dur):
                combined.append(WordTimestamp(word=w.word, start=w.start + offset_s, end=w.end + offset_s))
            offset_s += dur
            temp_paths.append(tmp)

        if not temp_paths:
            _synthesize_tts_to_wav(
                kokoro_model_id=kokoro_model_id,
                text=" ",
                out_wav_path=out_wav_path,
                pyttsx3_voice_id=voice_ids[0],
                kokoro_speaker=None,
                voice_instruction=None,
                elevenlabs_voice_id=None,
                elevenlabs_api_key=None,
                ffmpeg_executable=None,
                only_pyttsx3=True,
            )
            combined = _simple_word_timestamps(text=" ", total_s=_duration_seconds(out_wav_path))
        else:
            concat_pcm16_wavs(temp_paths, out_wav_path)

        payload = [{"word": w.word, "start": w.start, "end": w.end} for w in combined]
        out_captions_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        dprint("voice", "synthesize_unhinged done", f"word_timestamps={len(combined)}")
        return combined
    finally:
        for p in temp_paths:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass


def synthesize_unhinged_rotating_kokoro(
    *,
    kokoro_model_id: str,
    segment_texts: list[str],
    out_wav_path: Path,
    out_captions_json: Path,
    kokoro_speaker: str | None = None,
    voice_quant_mode: str | None = None,
) -> list[WordTimestamp]:
    """
    Unhinged format: one segment per non-empty part, rotating **af_bella → af_nicole → am_adam**
    when the per-character speaker is unset; otherwise reuse the same custom speaker for every segment.
    """
    from debug import dprint

    dprint("voice", "synthesize_unhinged_kokoro", f"segments={len(segment_texts)}")
    out_captions_json.parent.mkdir(parents=True, exist_ok=True)
    offset_s = 0.0
    combined: list[WordTimestamp] = []
    temp_paths: list[Path] = []
    seg_i = 0
    tts_i = 0
    try:
        for text in segment_texts:
            t = (text or "").strip()
            if not t:
                continue
            sp = kokoro_speaker_for_unhinged_segment(kokoro_speaker, tts_i)
            tts_i += 1
            tmp = out_wav_path.parent / f"_unhinged_kok_{seg_i:03d}.wav"
            seg_i += 1
            with vram_guard():
                ok = try_kokoro_tts(
                    model_id=kokoro_model_id,
                    text=t,
                    out_wav=tmp,
                    speaker=sp,
                    quant_mode=voice_quant_mode,
                )
                if not ok:
                    _pyttsx3_tts(t, tmp, None)
            dur = _duration_seconds(tmp)
            for w in _simple_word_timestamps(text=t, total_s=dur):
                combined.append(WordTimestamp(word=w.word, start=w.start + offset_s, end=w.end + offset_s))
            offset_s += dur
            temp_paths.append(tmp)

        if not temp_paths:
            sp0 = pick_kokoro_speaker(kokoro_speaker)
            with vram_guard():
                ok0 = try_kokoro_tts(
                    model_id=kokoro_model_id,
                    text=" ",
                    out_wav=out_wav_path,
                    speaker=sp0,
                    quant_mode=voice_quant_mode,
                )
                if not ok0:
                    _pyttsx3_tts(" ", out_wav_path, None)
            combined = _simple_word_timestamps(text=" ", total_s=_duration_seconds(out_wav_path))
        else:
            concat_pcm16_wavs(temp_paths, out_wav_path)

        payload = [{"word": w.word, "start": w.start, "end": w.end} for w in combined]
        out_captions_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        dprint("voice", "synthesize_unhinged_kokoro done", f"word_timestamps={len(combined)}")
        return combined
    finally:
        for p in temp_paths:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass


def synthesize_unhinged_moss(
    *,
    kokoro_model_id: str,
    voice_instruction: str | None,
    segment_texts: list[str],
    out_wav_path: Path,
    out_captions_json: Path,
    voice_quant_mode: str | None = None,
    voice_cuda_device_index: int | None = None,
) -> list[WordTimestamp]:
    """Unhinged: synthesize each segment with the same MOSS *instruction* + segment text, then concat."""
    from debug import dprint

    inst = (voice_instruction or "").strip() or DEFAULT_MOSS_INSTRUCTION
    dprint("voice", "synthesize_unhinged_moss", f"segments={len(segment_texts)}")
    if is_pyttsx3_fallback_repo(kokoro_model_id):
        return synthesize_unhinged_rotating_pyttsx3(
            kokoro_model_id=kokoro_model_id,
            segment_texts=segment_texts,
            out_wav_path=out_wav_path,
            out_captions_json=out_captions_json,
        )
    out_captions_json.parent.mkdir(parents=True, exist_ok=True)
    offset_s = 0.0
    combined: list[WordTimestamp] = []
    temp_paths: list[Path] = []
    seg_i = 0
    try:
        for text in segment_texts:
            t = (text or "").strip()
            if not t:
                continue
            tmp = out_wav_path.parent / f"_unhinged_moss_{seg_i:03d}.wav"
            seg_i += 1
            with vram_guard():
                ok = try_moss_voicegenerator_tts(
                    model_id=kokoro_model_id,
                    text=t,
                    instruction=inst,
                    out_wav=tmp,
                    quant_mode=voice_quant_mode,
                    cuda_voice_device_index=voice_cuda_device_index,
                )
                if not ok:
                    _pyttsx3_tts(t, tmp, None)
            dur = _duration_seconds(tmp)
            for w in _simple_word_timestamps(text=t, total_s=dur):
                combined.append(WordTimestamp(word=w.word, start=w.start + offset_s, end=w.end + offset_s))
            offset_s += dur
            temp_paths.append(tmp)

        if not temp_paths:
            with vram_guard():
                if not try_moss_voicegenerator_tts(
                    model_id=kokoro_model_id,
                    text=" ",
                    instruction=inst,
                    out_wav=out_wav_path,
                    quant_mode=voice_quant_mode,
                    cuda_voice_device_index=voice_cuda_device_index,
                ):
                    _pyttsx3_tts(" ", out_wav_path, None)
            combined = _simple_word_timestamps(text=" ", total_s=_duration_seconds(out_wav_path))
        else:
            concat_pcm16_wavs(temp_paths, out_wav_path)

        payload = [{"word": w.word, "start": w.start, "end": w.end} for w in combined]
        out_captions_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        dprint("voice", "synthesize_unhinged_moss done", f"word_timestamps={len(combined)}")
        return combined
    finally:
        for p in temp_paths:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

