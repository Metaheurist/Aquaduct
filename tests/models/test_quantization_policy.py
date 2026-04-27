from __future__ import annotations

from src.core.config import AppSettings
from src.models.quantization import (
    PredictedVram,
    mode_label,
    normalize_settings_quant_modes,
    parse_vram_hint_gb,
    pick_auto_mode,
    predict_vram_gb,
    resolve_quant_mode,
    supported_quant_modes,
)


def test_mode_labels_cover_canonical_modes() -> None:
    for m in ("auto", "bf16", "fp16", "int8", "nf4_4bit", "cpu_offload"):
        assert mode_label(m), f"missing label for {m}"


def test_supported_modes_script_includes_4bit() -> None:
    modes = supported_quant_modes(role="script")
    names = {opt.mode for opt in modes}
    assert {"auto", "bf16", "fp16", "int8", "nf4_4bit"}.issubset(names)


def test_supported_modes_image_video_include_cpu_offload() -> None:
    for role in ("image", "video"):
        modes = supported_quant_modes(role=role)
        names = {opt.mode for opt in modes}
        assert "cpu_offload" in names
        assert "auto" in names


def test_supported_modes_voice_kokoro_marks_unsupported_disabled() -> None:
    modes = supported_quant_modes(role="voice", repo_id="hexgrad/Kokoro-82M")
    enabled = {opt.mode: opt.enabled for opt in modes}
    assert enabled["auto"] is True
    # Non-auto kokoro modes should be disabled (passthrough metadata only).
    for m in ("bf16", "fp16", "int8", "nf4_4bit"):
        assert enabled[m] is False


def test_normalize_settings_quant_modes_handles_aliases() -> None:
    s = AppSettings(
        script_quant_mode="4bit",  # type: ignore[arg-type]
        image_quant_mode="8bit",  # type: ignore[arg-type]
        video_quant_mode="cpu",  # type: ignore[arg-type]
        voice_quant_mode="bogus",  # type: ignore[arg-type]
    )
    n = normalize_settings_quant_modes(s)
    assert n.script_quant_mode == "nf4_4bit"
    assert n.image_quant_mode == "int8"
    assert n.video_quant_mode == "cpu_offload"
    assert n.voice_quant_mode == "auto"


def test_predict_vram_lowers_with_4bit_for_script() -> None:
    base = predict_vram_gb(role="script", repo_id="x", base_low_gb=14, base_high_gb=18, mode="fp16")
    quant = predict_vram_gb(role="script", repo_id="x", base_low_gb=14, base_high_gb=18, mode="nf4_4bit")
    assert isinstance(base, PredictedVram)
    assert isinstance(quant, PredictedVram)
    assert quant.high_gb is not None and base.high_gb is not None
    assert quant.high_gb < base.high_gb
    # NF4 should be roughly ~38% of fp16 weight memory (with some tolerance).
    assert quant.high_gb / base.high_gb < 0.5


def test_parse_vram_hint_gb_handles_ranges_and_singles() -> None:
    assert parse_vram_hint_gb("~ 6-8 GB VRAM") == (6.0, 8.0)
    assert parse_vram_hint_gb("~ 24-40+ GB VRAM") == (24.0, 40.0)
    lo, hi = parse_vram_hint_gb("~ 12 GB VRAM")
    assert lo == 12.0 and hi == 12.0
    assert parse_vram_hint_gb("") == (None, None)
    assert parse_vram_hint_gb("--") == (None, None)


def test_pick_auto_mode_script_low_vram_picks_4bit() -> None:
    assert pick_auto_mode(role="script", repo_id="", vram_gb=6.0, cuda_ok=True) == "nf4_4bit"
    assert pick_auto_mode(role="script", repo_id="", vram_gb=12.0, cuda_ok=True) == "int8"
    assert pick_auto_mode(role="script", repo_id="", vram_gb=18.0, cuda_ok=True) == "fp16"
    assert pick_auto_mode(role="script", repo_id="", vram_gb=24.0, cuda_ok=True) == "bf16"


def test_pick_auto_mode_diffusion_falls_back_to_cpu_offload_when_no_cuda() -> None:
    assert pick_auto_mode(role="image", repo_id="", vram_gb=None, cuda_ok=False) == "cpu_offload"
    assert pick_auto_mode(role="video", repo_id="", vram_gb=4.0, cuda_ok=True) == "cpu_offload"


def test_resolve_quant_mode_returns_explicit_value() -> None:
    s = AppSettings(script_quant_mode="nf4_4bit")  # type: ignore[arg-type]
    assert resolve_quant_mode(role="script", settings=s) == "nf4_4bit"


def test_resolve_quant_mode_auto_resolves_to_concrete(monkeypatch) -> None:
    # When script_quant_mode is "auto" and resolver returns a known VRAM, we should
    # pick a concrete mode based on pick_auto_mode rules.
    s = AppSettings(script_quant_mode="auto")  # type: ignore[arg-type]
    monkeypatch.setattr(
        "src.models.inference_profiles.resolve_effective_vram_gb",
        lambda *, kind, settings: 6.0,
    )
    assert resolve_quant_mode(role="script", settings=s) == "nf4_4bit"
