from __future__ import annotations

from src.personality_auto import auto_pick_personality


def test_auto_pick_rules_urgent():
    r = auto_pick_personality(
        requested_id="auto",
        llm_model_id="unused",
        titles=["Breaking: new AI tool leaked today", "Just dropped: Agents platform"],
        topic_tags=[],
    )
    assert r.preset.id in {"urgent", "hype"}


def test_auto_pick_manual_passthrough():
    r = auto_pick_personality(
        requested_id="analytical",
        llm_model_id="unused",
        titles=["Anything"],
        topic_tags=[],
    )
    assert r.preset.id == "analytical"


def test_auto_pick_close_tie_still_returns_preset():
    r = auto_pick_personality(
        requested_id="auto",
        llm_model_id="unused",
        titles=["New AI tool released"],
        topic_tags=[],
    )
    assert r.preset.id in {"neutral", "hype", "analytical", "urgent", "cozy", "skeptical", "contrarian", "comedic"}
    assert "Rules" in r.reason


def test_factcheck_extract_claims_finds_numbers_and_superlatives():
    from src.factcheck import extract_claims

    claims = extract_claims("It is 30% faster and the best tool ever. It always works.")
    kinds = {c.kind for c in claims}
    assert "number" in kinds
    assert "superlative" in kinds
    assert "absolute" in kinds

