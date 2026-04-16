from __future__ import annotations

import math
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .utils_ffmpeg import ensure_ffmpeg


@dataclass(frozen=True)
class AudioPolishConfig:
    mode: str  # off | basic | strong
    target_lufs: float = -16.0


@dataclass(frozen=True)
class MusicMixConfig:
    enabled: bool
    ducking_enabled: bool = True
    ducking_amount: float = 0.7  # higher = more duck
    fade_s: float = 1.2
    music_volume: float = 0.08


@dataclass(frozen=True)
class SfxConfig:
    enabled: bool
    mode: str = "subtle"  # subtle


def _duration_seconds(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as w:
        frames = w.getnframes()
        sr = w.getframerate()
    return frames / float(sr)


def duration_seconds(wav_path: Path) -> float:
    return _duration_seconds(wav_path)


def ensure_builtin_sfx(dir_path: Path) -> dict[str, Path]:
    """
    Create tiny built-in SFX wavs if missing. Returns dict of paths.
    """
    dir_path.mkdir(parents=True, exist_ok=True)
    whoosh = dir_path / "whoosh.wav"
    click = dir_path / "click.wav"

    sr = 44100

    if not whoosh.exists():
        dur = 0.22
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        # downward chirp + noise
        f0, f1 = 1400.0, 200.0
        k = (f1 - f0) / dur
        phase = 2 * math.pi * (f0 * t + 0.5 * k * t * t)
        sig = 0.18 * np.sin(phase)
        sig += 0.03 * np.random.RandomState(0).normal(size=n)
        # fade in/out
        env = np.sin(np.linspace(0, math.pi, n)) ** 2
        sig = (sig * env).astype(np.float32)
        sf.write(str(whoosh), sig, sr, subtype="PCM_16")

    if not click.exists():
        dur = 0.03
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        sig = 0.25 * np.sin(2 * math.pi * 2000.0 * t)
        env = np.exp(-t * 90.0)
        sig = (sig * env).astype(np.float32)
        sf.write(str(click), sig, sr, subtype="PCM_16")

    return {"whoosh": whoosh, "click": click}


def build_voice_process_cmd(*, ffmpeg: Path, in_wav: Path, out_wav: Path, cfg: AudioPolishConfig) -> list[str]:
    if cfg.mode == "off":
        return []

    # Basic chain: loudnorm -> compressor/compand -> limiter
    # Keep it conservative to avoid pumping artifacts.
    if cfg.mode == "strong":
        comp = "acompressor=threshold=-18dB:ratio=4:attack=15:release=200:makeup=6"
        lim = "alimiter=limit=0.95:level=0.95"
    else:
        comp = "acompressor=threshold=-20dB:ratio=2.5:attack=20:release=250:makeup=4"
        lim = "alimiter=limit=0.97:level=0.97"

    af = f"loudnorm=I={cfg.target_lufs}:TP=-1.5:LRA=11,{comp},{lim}"
    return [str(ffmpeg), "-y", "-i", str(in_wav), "-vn", "-af", af, str(out_wav)]


def process_voice_wav(*, ffmpeg_dir: Path, in_wav: Path, out_wav: Path, cfg: AudioPolishConfig) -> Path:
    if cfg.mode == "off":
        return in_wav
    ffmpeg = Path(ensure_ffmpeg(ffmpeg_dir))
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_voice_process_cmd(ffmpeg=ffmpeg, in_wav=in_wav, out_wav=out_wav, cfg=cfg)
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_wav


def build_music_duck_cmd(
    *,
    ffmpeg: Path,
    voice_wav: Path,
    music_path: Path,
    out_wav: Path,
    cfg: MusicMixConfig,
) -> list[str]:
    # Inputs: voice (0) and music (1)
    # 1) scale music volume
    # 2) sidechaincompress music keyed by voice
    # 3) fade in/out music
    # 4) mix voice + processed music
    fade = max(0.0, float(cfg.fade_s))
    duck = ""
    if cfg.ducking_enabled:
        # ratio-ish behavior via sidechaincompress
        duck = f",sidechaincompress=threshold=0.02:ratio=10:attack=20:release=250"
    music_vol = max(0.0, float(cfg.music_volume))
    af = (
        f"[1:a]volume={music_vol:.4f}{duck},"
        f"afade=t=in:st=0:d={fade:.3f},"
        f"afade=t=out:st=0:d={fade:.3f}[mb];"
        f"[0:a][mb]amix=inputs=2:normalize=0:duration=first[aout]"
    )
    return [
        str(ffmpeg),
        "-y",
        "-i",
        str(voice_wav),
        "-i",
        str(music_path),
        "-filter_complex",
        af,
        "-map",
        "[aout]",
        "-c:a",
        "pcm_s16le",
        str(out_wav),
    ]


def mix_voice_and_music(*, ffmpeg_dir: Path, voice_wav: Path, music_path: Path, out_wav: Path, cfg: MusicMixConfig) -> Path:
    ffmpeg = Path(ensure_ffmpeg(ffmpeg_dir))
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_music_duck_cmd(ffmpeg=ffmpeg, voice_wav=voice_wav, music_path=music_path, out_wav=out_wav, cfg=cfg)
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_wav


def build_sfx_mix_cmd(
    *,
    ffmpeg: Path,
    base_wav: Path,
    sfx_wavs: list[Path],
    out_wav: Path,
) -> list[str]:
    # Mix base + N sfx tracks
    cmd = [str(ffmpeg), "-y", "-i", str(base_wav)]
    for p in sfx_wavs:
        cmd += ["-i", str(p)]
    inputs = 1 + len(sfx_wavs)
    cmd += [
        "-filter_complex",
        f"amix=inputs={inputs}:normalize=0:duration=first",
        "-c:a",
        "pcm_s16le",
        str(out_wav),
    ]
    return cmd


def render_sfx_track(*, sr: int, duration_s: float, events: list[tuple[float, Path, float]], out_wav: Path) -> Path:
    """
    Render a single-channel sfx bed from event list: (time_s, wav_path, gain).
    """
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    n = int(sr * max(0.1, float(duration_s)))
    bed = np.zeros(n, dtype=np.float32)

    for t0, wav_path, gain in events:
        try:
            sig, in_sr = sf.read(str(wav_path), dtype="float32")
        except Exception:
            continue
        if sig.ndim > 1:
            sig = sig[:, 0]
        if in_sr != sr:
            # cheap resample
            x = np.linspace(0, 1, len(sig), endpoint=False)
            xi = np.linspace(0, 1, int(len(sig) * (sr / float(in_sr))), endpoint=False)
            sig = np.interp(xi, x, sig).astype(np.float32)
        start = int(max(0.0, float(t0)) * sr)
        end = min(n, start + len(sig))
        if start >= n:
            continue
        bed[start:end] += (sig[: end - start] * float(gain)).astype(np.float32)

    sf.write(str(out_wav), bed, sr, subtype="PCM_16")
    return out_wav


def schedule_sfx_events(*, duration_s: float, clip_count: int, sfx_paths: dict[str, Path]) -> list[tuple[float, Path, float]]:
    """
    Very simple scheduler:
    - whoosh on clip boundaries
    - occasional click on midpoints
    """
    events: list[tuple[float, Path, float]] = []
    if clip_count <= 1:
        return events
    whoosh = sfx_paths.get("whoosh")
    click = sfx_paths.get("click")
    chunk = float(duration_s) / float(clip_count)
    for i in range(1, clip_count):
        t = max(0.0, i * chunk - 0.05)
        if whoosh:
            events.append((t, whoosh, 0.35))
        if click and (i % 2 == 0):
            events.append((i * chunk + 0.02, click, 0.25))
    return events

