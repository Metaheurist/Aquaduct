from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.voice import concat_pcm16_wavs


def test_concat_pcm16_wavs_same_sample_rate(tmp_path: Path) -> None:
    pytest.importorskip("numpy")
    p1 = tmp_path / "a.wav"
    p2 = tmp_path / "b.wav"
    sr = 22050
    a = np.zeros(100, dtype=np.float32)
    b = np.ones(50, dtype=np.float32) * 0.01
    sf.write(str(p1), a, sr, subtype="PCM_16")
    sf.write(str(p2), b, sr, subtype="PCM_16")
    out = tmp_path / "out.wav"
    concat_pcm16_wavs([p1, p2], out)
    data, sr_out = sf.read(str(out), dtype="float32")
    assert sr_out == sr
    assert data.shape[0] == 150


def test_concat_pcm16_wavs_resamples_second_to_first(tmp_path: Path) -> None:
    pytest.importorskip("numpy")
    p1 = tmp_path / "a.wav"
    p2 = tmp_path / "b.wav"
    a = np.zeros(1000, dtype=np.float32)
    b = np.ones(500, dtype=np.float32) * 0.01
    sf.write(str(p1), a, 22050, subtype="PCM_16")
    sf.write(str(p2), b, 44100, subtype="PCM_16")
    out = tmp_path / "out.wav"
    concat_pcm16_wavs([p1, p2], out)
    data, sr_out = sf.read(str(out), dtype="float32")
    assert sr_out == 22050
    assert data.shape[0] > 1000
