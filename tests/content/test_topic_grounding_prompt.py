"""Prompt shape for topic-tag grounding (LLM JSON batch)."""

from src.content.brain import _prompt_topic_tag_grounding_batch


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
