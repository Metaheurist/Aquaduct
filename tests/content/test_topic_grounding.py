"""Topic grounding: tag batching and LLM prompt shape."""

from __future__ import annotations

from src.content.brain import (
    TOPIC_GROUNDING_MAX_TAGS_PER_CHUNK,
    _prompt_topic_tag_grounding_batch,
    topic_grounding_pair_chunks,
)


def test_topic_grounding_pair_chunks_default_size() -> None:
    pairs = [(str(i), f"D{i}") for i in range(TOPIC_GROUNDING_MAX_TAGS_PER_CHUNK + 2)]
    chunks = topic_grounding_pair_chunks(pairs)
    assert len(chunks) == 2
    assert len(chunks[0]) == TOPIC_GROUNDING_MAX_TAGS_PER_CHUNK
    assert len(chunks[1]) == 2


def test_topic_grounding_pair_chunks_custom_size_and_empty() -> None:
    assert topic_grounding_pair_chunks([], chunk_size=3) == []
    p = [("a", "A"), ("b", "B"), ("c", "C")]
    assert topic_grounding_pair_chunks(p, chunk_size=1) == [[("a", "A")], [("b", "B")], [("c", "C")]]
    assert topic_grounding_pair_chunks(p, chunk_size=10) == [p]


def test_topic_grounding_prompt_leads_with_json_schema() -> None:
    body = _prompt_topic_tag_grounding_batch(
        [("ghost", "Ghost Stories"), ("folk horror", "Folk Horror")],
        "news",
        sibling_displays=["Ghost Stories", "Folk Horror"],
        seed_notes_by_norm=None,
    )
    assert body.startswith("JSON schema")
    assert '{"notes":' in body
    assert "• json key EXACTLY" not in body
    assert "ghost\tGhost Stories" in body
    assert "folk horror\tFolk Horror" in body


def test_topic_grounding_prompt_seed_column_when_present() -> None:
    body = _prompt_topic_tag_grounding_batch(
        [("climate", "Climate")],
        "explainer",
        sibling_displays=["Climate"],
        seed_notes_by_norm={"climate": "Keep IPCC tone"},
    )
    assert "climate\tClimate\tKeep IPCC tone" in body
