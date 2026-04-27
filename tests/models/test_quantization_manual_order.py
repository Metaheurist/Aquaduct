"""Ordering of enabled manual quant modes for the Model tab slider (low VRAM → higher quality)."""

from src.models.quantization import manual_quant_modes_low_to_high


def test_script_manual_order_stable() -> None:
    modes = manual_quant_modes_low_to_high(role="script", repo_id="meta-llama/Llama-3.2-3B-Instruct")
    assert modes == ("nf4_4bit", "int8", "fp16", "bf16")


def test_image_manual_order_cpu_offload_first() -> None:
    modes = manual_quant_modes_low_to_high(role="image", repo_id="black-forest-labs/FLUX.1-schnell")
    assert modes == ("cpu_offload", "int8", "fp16", "bf16")


def test_video_manual_order_matches_image_family() -> None:
    modes = manual_quant_modes_low_to_high(role="video", repo_id="cerspense/zeroscope_v2_576w")
    assert modes[0] == "cpu_offload"


def test_kokoro_voice_has_no_manual_modes() -> None:
    modes = manual_quant_modes_low_to_high(role="voice", repo_id="hexgrad/Kokoro-82M")
    assert modes == ()


def test_non_kokoro_voice_manual_order_matches_script_family() -> None:
    modes = manual_quant_modes_low_to_high(role="voice", repo_id="some/MOSS-VoiceGenerator")
    assert modes[0] == "nf4_4bit"
    assert modes[-1] == "bf16"
