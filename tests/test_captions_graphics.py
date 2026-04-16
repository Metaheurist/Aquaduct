from __future__ import annotations

import numpy as np

from src.captions import CaptionWord, caption_window_for_time, render_caption_overlay_rgba
from src.config import VideoSettings
from src.facts_card import extract_candidate_facts, pick_top_facts


def test_caption_window_active_word():
    words = [
        CaptionWord("a", 0.0, 0.2),
        CaptionWord("b", 0.2, 0.4),
        CaptionWord("c", 0.4, 0.6),
    ]
    ws, idxs, active = caption_window_for_time(words, 0.45, max_words=8)
    assert "c" in ws
    assert active >= 0


def test_render_caption_non_empty_rgba():
    words = [CaptionWord("hello", 0.0, 0.5), CaptionWord("world", 0.5, 1.0)]
    vs = VideoSettings(width=1080, height=1920, captions_enabled=True, caption_highlight_intensity="strong")
    arr = render_caption_overlay_rgba(
        word_strings=["hello", "world"],
        window_indices=[0, 1],
        active_in_window=0,
        all_words=words,
        w=1080,
        h=1920,
        branding=None,
        settings=vs,
        topic_tags=[],
    )
    assert arr.shape == (1920, 1080, 4)
    assert arr.shape[2] == 4
    assert np.any(arr[:, :, 3] > 0)
    # Strong mode: highlight pill behind first word → elevated alpha in lower-third band
    band = arr[int(1920 * 0.60) : int(1920 * 0.92), :, 3]
    assert np.max(band) >= 80


def test_wrap_preserves_all_words_long_window():
    from src.captions import _wrap_words_to_lines
    from PIL import Image, ImageDraw, ImageFont

    words = [f"w{i}" for i in range(14)]
    img = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        font = ImageFont.load_default()
    lines = _wrap_words_to_lines(words, font, draw, max_width=200)
    flat = [t for ln in lines for t in ln]
    assert len(flat) == len(words)


def test_fact_extraction_finds_percent():
    text = "The market rose 12.5% in Q3, and revenue hit $3.2 million according to reports."
    facts = extract_candidate_facts(text)
    assert facts
    picked = pick_top_facts(facts, n=2)
    assert len(picked) >= 1
    assert any("%" in p or "$" in p for p in picked)
