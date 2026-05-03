"""Phase 6 tests for ``src/content/topic_constraints.py``.

Pure-Python coverage of:

- ``normalize_tags`` — case-insensitive dedupe, empty drop.
- ``topic_constraints_block`` — produces a HARD-tagged block with notes
  and cast names, returns "" for empty input.
- ``topic_constraints_json`` — JSON mirror, picks up notes.
- ``score_source_url`` — high / mid / low / unknown badges, reason
  messages, body-length nudges.
- ``sanitize_topic_tag_notes`` — coerces messy persisted dicts into a
  clean ``{tag_lower: note}`` mapping.
- ``parse_topic_grounding_llm_json`` — batch LLM helper for per-tag notes.
"""
from __future__ import annotations

import json

import pytest

from src.content import topic_constraints as tc


def test_normalize_tags_dedupes_and_lowercases() -> None:
    assert tc.normalize_tags(["AI", "ai", "  AI  ", "Robots", "Robots", ""]) == ["ai", "robots"]


def test_topic_constraints_block_empty_returns_blank() -> None:
    assert tc.topic_constraints_block(None) == ""
    assert tc.topic_constraints_block([]) == ""
    assert tc.topic_constraints_block(["", "  "]) == ""


def test_topic_constraints_block_includes_hard_marker_and_tags() -> None:
    block = tc.topic_constraints_block(["folk-horror", "1990s"])
    assert "HARD" in block
    assert "`folk-horror`" in block
    assert "`1990s`" in block
    assert "Cast:" not in block


def test_topic_constraints_block_attaches_notes() -> None:
    block = tc.topic_constraints_block(
        ["folk-horror"],
        notes={"FOLK-HORROR": "rural setting, bonfire night"},
    )
    assert "rural setting, bonfire night" in block


def test_topic_constraints_block_includes_cast_names() -> None:
    block = tc.topic_constraints_block(
        ["nature"],
        cast_names=["Mara Vex", "Foil Plenty"],
    )
    assert "Mara Vex" in block
    assert "Foil Plenty" in block


def test_topic_constraints_block_caps_cast_at_four() -> None:
    cast = [f"Char{i}" for i in range(8)]
    block = tc.topic_constraints_block(["nature"], cast_names=cast)
    for i in range(4):
        assert f"Char{i}" in block
    assert "Char5" not in block


def test_topic_constraints_json_mirrors_notes() -> None:
    out = tc.topic_constraints_json(
        ["a", "b"],
        notes={"a": "first note"},
    )
    payload = json.loads(out)
    assert payload[0] == {"tag": "a", "note": "first note"}
    assert payload[1] == {"tag": "b"}


def test_topic_constraints_json_empty_returns_blank() -> None:
    assert tc.topic_constraints_json([]) == ""


@pytest.mark.parametrize(
    "url,expected_badge",
    [
        ("https://en.wikipedia.org/wiki/Test", "high"),
        ("https://www.bbc.com/news/article", "high"),
        ("https://creepypasta.fandom.com/wiki/Test", "high"),
        ("https://medium.com/@user/post", "mid"),
        ("https://substack.com/p/post", "mid"),
        ("https://random.tk/page", "low"),
        ("https://promo-site.com", "low"),
    ],
)
def test_score_source_url_known_domains(url: str, expected_badge: str) -> None:
    q = tc.score_source_url(url)
    assert q.badge == expected_badge
    assert 0 <= q.score <= 100


def test_score_source_url_unknown_url_returns_unknown_badge() -> None:
    q = tc.score_source_url("")
    assert q.badge == "unknown"
    assert q.score == 0


def test_score_source_url_long_body_increases_score() -> None:
    short = tc.score_source_url("https://example.com/page", body_length=100)
    long_ = tc.score_source_url("https://example.com/page", body_length=12000)
    assert long_.score >= short.score
    assert any("≥4k" in r for r in long_.reasons)


def test_score_source_url_short_body_decreases_score() -> None:
    short = tc.score_source_url("https://example.com/page", body_length=200)
    assert any("<600" in r for r in short.reasons)


def test_source_quality_label_handles_none() -> None:
    assert tc.source_quality_label(None) == "unknown"


def test_source_quality_label_format() -> None:
    q = tc.SourceQuality(score=72, badge="mid", reasons=("test",))
    assert tc.source_quality_label(q) == "MID (72)"


def test_sanitize_topic_tag_notes_drops_empty_and_lowercases() -> None:
    raw = {
        "AI": "use modern frame",
        "  ai ": "duplicate ignored",
        "robots": "",
        "": "ignored",
        "Folk-Horror": "  rural   bonfire  ",
    }
    out = tc.sanitize_topic_tag_notes(raw)
    assert "ai" in out
    assert "folk-horror" in out
    assert "robots" not in out
    assert out["folk-horror"] == "rural   bonfire"


def test_sanitize_topic_tag_notes_strips_control_chars() -> None:
    out = tc.sanitize_topic_tag_notes({"x": "ok\x00bad"})
    assert out["x"] == "ok bad"


def test_sanitize_topic_tag_notes_caps_length() -> None:
    out = tc.sanitize_topic_tag_notes({"x": "a" * 500})
    assert len(out["x"]) == 240


def test_topic_notes_for_case_insensitive_lookup() -> None:
    assert tc.topic_notes_for({"Tag-A": "hi"}, "tag-a") == "hi"
    assert tc.topic_notes_for({"tag-a": "hi"}, "TAG-A") == "hi"
    assert tc.topic_notes_for(None, "x") == ""
    assert tc.topic_notes_for({}, "x") == ""


def test_parse_topic_grounding_llm_json_nested_notes_shape() -> None:
    allowed = frozenset({"ghost", "folk horror"})
    raw = '{"notes": {"ghost": " keep first-person unease ", "folk horror": "rural dread, no gore"}} extra'
    out, missing = tc.parse_topic_grounding_llm_json(raw, allowed_normalized_tags=allowed)
    assert out["ghost"] == "keep first-person unease"
    assert "folk horror" in out
    assert missing == tuple()


def test_parse_topic_grounding_llm_json_flat_object_and_missing() -> None:
    allowed = frozenset({"a", "b"})
    raw = '{"a": "one", "noise": "ignored"}'
    out, missing = tc.parse_topic_grounding_llm_json(raw, allowed_normalized_tags=allowed)
    assert out == {"a": "one"}
    assert missing == ("b",)


def test_parse_topic_grounding_llm_json_raises_on_non_json() -> None:
    with pytest.raises(ValueError):
        tc.parse_topic_grounding_llm_json("hello", allowed_normalized_tags=frozenset({"x"}))
