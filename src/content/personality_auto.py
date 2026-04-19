from __future__ import annotations

import re
from dataclasses import dataclass

from .personalities import PersonalityPreset, get_personality_by_id, get_personality_presets


@dataclass(frozen=True)
class AutoPickResult:
    preset: PersonalityPreset
    reason: str


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _score_rules(*, titles: list[str], topic_tags: list[str], extra_scoring_text: str = "") -> dict[str, int]:
    parts = [_norm(t) for t in titles] + [_norm(t) for t in topic_tags]
    ex = _norm(extra_scoring_text)
    if ex:
        parts.append(ex)
    text = " ".join(parts)

    scores = {p.id: 0 for p in get_personality_presets()}

    def bump(pid: str, n: int = 1) -> None:
        if pid in scores:
            scores[pid] += n

    # Keyword heuristics
    if any(k in text for k in ["breaking", "just dropped", "leak", "today", "right now", "urgent"]):
        bump("urgent", 4)
        bump("hype", 1)

    if any(k in text for k in ["benchmark", "paper", "study", "research", "technical", "open-source", "release notes", "latency"]):
        bump("analytical", 4)

    if any(k in text for k in ["scam", "myth", "does it actually", "real or", "marketing", "hallucinat", "privacy", "security"]):
        bump("skeptical", 4)

    if any(
        k in text
        for k in [
            "funny",
            "meme",
            "roast",
            "lol",
            "wild",
            "crazy",
            "cartoon",
            "animation",
            "comedy",
            "comedic",
            "satire",
            "skit",
            "stand-up",
            "parody",
        ]
    ):
        bump("comedic", 3)
        bump("hype", 1)

    if any(k in text for k in ["tutorial", "beginner", "simple", "explainer", "how to", "for beginners"]):
        bump("cozy", 3)
        bump("neutral", 1)

    if any(k in text for k in ["hot take", "unpopular", "actually", "everyone thinks", "here's why that's wrong"]):
        bump("contrarian", 4)
        bump("skeptical", 1)

    # Topic tag bias — dev stack (soften when comedy/cartoon entertainment signals dominate)
    dev_hit = any(k in text for k in ["agent", "workflow", "ide", "dev", "api", "cli", "docker", "rag", "llm"])
    comedy_ent_hit = any(
        k in text for k in ["cartoon", "animation", "comedy", "satire", "skit", "meme", "funny", "tiktok comedy"]
    )
    if dev_hit:
        bump("analytical", 1 if comedy_ent_hit else 2)

    if any(k in text for k in ["productivity", "creator", "editing", "video", "tiktok", "shorts"]):
        bump("hype", 2)
        bump("cozy", 1)

    # Default baseline
    bump("neutral", 1)

    return scores


def _top2(scores: dict[str, int]) -> tuple[tuple[str, int], tuple[str, int]]:
    items = sorted(scores.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    a = items[0] if items else ("neutral", 0)
    b = items[1] if len(items) > 1 else ("neutral", 0)
    return a, b


def auto_pick_personality(
    *,
    requested_id: str,
    llm_model_id: str,
    titles: list[str],
    topic_tags: list[str],
    extra_scoring_text: str = "",
) -> AutoPickResult:
    """
    Rules-based auto personality. ``llm_model_id`` is kept for call-site compatibility only.

    We intentionally do **not** call the LLM here: a previous design used a "tie-break"
    generation step that loaded the full model before ``generate_script``, which duplicated
    work and could stall the UI for minutes at "Choosing personality…".
    """
    _ = llm_model_id
    rid = (requested_id or "").strip().lower()
    if rid and rid != "auto":
        p = get_personality_by_id(rid)
        return AutoPickResult(preset=p, reason="Manual selection")

    scores = _score_rules(titles=titles, topic_tags=topic_tags, extra_scoring_text=extra_scoring_text)
    (a_id, a_score), (b_id, b_score) = _top2(scores)

    tie_band = 1
    if abs(a_score - b_score) <= tie_band:
        reason = f"Rules (close tie): {a_id} ({a_score}) vs {b_id} ({b_score}); picked top"
    else:
        reason = f"Rules: {a_id} ({a_score})"

    return AutoPickResult(preset=get_personality_by_id(a_id), reason=reason)
