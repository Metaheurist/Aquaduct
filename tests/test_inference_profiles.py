"""VRAM-band inference profiles (no GPU required)."""

from __future__ import annotations

from src.core.config import AppSettings
from src.models import inference_profiles as ip


def test_vram_to_band():
    assert ip.vram_gb_to_band(None) == "unknown"
    assert ip.vram_gb_to_band(0) == "unknown"
    assert ip.vram_gb_to_band(4) == "lt_8"
    assert ip.vram_gb_to_band(10) == "8_12"
    assert ip.vram_gb_to_band(14) == "12_16"
    assert ip.vram_gb_to_band(20) == "16_24"
    assert ip.vram_gb_to_band(32) == "24_40"
    assert ip.vram_gb_to_band(48) == "ge_40"


def test_merge_t2i_overrides_baseline():
    base = {
        "guidance_scale": 7.0,
        "num_inference_steps": 99,
        "width": 1024,
        "height": 1024,
    }
    out = ip.merge_t2i_kwargs(
        base,
        "black-forest-labs/FLUX.1-schnell",
        8.0,
    )
    assert out["width"] < base["width"]
    assert "num_inference_steps" in out


def test_merge_t2v_ltx2_frame_rule():
    model = "lightricks/ltx-2"
    vkw = {"num_frames": 10, "height": 512, "width": 768, "num_inference_steps": 40}
    m = ip.merge_t2v_kwargs(vkw, model, 20.0)
    nf = int(m["num_frames"])
    assert (nf - 1) % 8 == 0


def test_format_report_does_not_crash():
    s = AppSettings()
    t = ip.format_inference_profile_report(s)
    assert "Autofit algorithm" in t
    assert "Script (LLM)" in t
