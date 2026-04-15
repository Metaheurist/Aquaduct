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


def test_auto_pick_tiebreak_llm_failure_falls_back(monkeypatch):
    # Force tie: neutral baseline, then make _llm_tiebreak return None
    import src.personality_auto as mod

    monkeypatch.setattr(mod, "_llm_tiebreak", lambda **kwargs: None)
    r = mod.auto_pick_personality(
        requested_id="auto",
        llm_model_id="unused",
        titles=["New AI tool released"],
        topic_tags=[],
    )
    assert r.preset.id in {"neutral", "hype", "analytical", "urgent", "cozy", "skeptical", "contrarian", "comedic"}

