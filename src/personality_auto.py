from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .personalities import PersonalityPreset, get_personality_by_id, get_personality_presets


@dataclass(frozen=True)
class AutoPickResult:
    preset: PersonalityPreset
    reason: str


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _score_rules(*, titles: list[str], topic_tags: list[str]) -> dict[str, int]:
    text = " ".join([_norm(t) for t in titles] + [_norm(t) for t in topic_tags])

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

    if any(k in text for k in ["funny", "meme", "roast", "lol", "wild", "crazy"]):
        bump("comedic", 3)
        bump("hype", 1)

    if any(k in text for k in ["tutorial", "beginner", "simple", "explainer", "how to", "for beginners"]):
        bump("cozy", 3)
        bump("neutral", 1)

    if any(k in text for k in ["hot take", "unpopular", "actually", "everyone thinks", "here's why that's wrong"]):
        bump("contrarian", 4)
        bump("skeptical", 1)

    # Topic tag bias
    if any(k in text for k in ["agent", "workflow", "ide", "dev", "api", "cli", "docker", "rag", "llm"]):
        bump("analytical", 2)

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


def _llm_tiebreak(
    *,
    model_id: str,
    titles: list[str],
    candidates: list[PersonalityPreset],
) -> str | None:
    """
    Best-effort: ask local LLM to choose a preset id among candidates.
    Returns preset id or None.
    """
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except Exception:
        return None

    cand_ids = [c.id for c in candidates]
    cand_labels = {c.id: c.label for c in candidates}

    prompt = (
        "Pick the best personality preset id for a short AI news video script.\n"
        f"Candidates: {json.dumps(cand_labels, ensure_ascii=False)}\n"
        f"Headlines: {json.dumps(titles[:6], ensure_ascii=False)}\n"
        "Output ONLY one of these ids exactly (no extra text): " + ", ".join(cand_ids) + "\n"
    )

    tok = AutoTokenizer.from_pretrained(model_id, use_fast=True)
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb,
        device_map="auto",
        torch_dtype=torch.float16,
    )

    inputs = tok(prompt, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        out = model.generate(
            **inputs,
            max_new_tokens=8,
            do_sample=False,
            eos_token_id=tok.eos_token_id,
        )
    text = tok.decode(out[0], skip_special_tokens=True)

    # Extract last token-ish
    tail = text.strip().split()[-1].strip().lower()
    if tail in cand_ids:
        return tail
    # Sometimes model echoes prompt; search for an id
    for cid in cand_ids:
        if re.search(rf"\b{re.escape(cid)}\b", text.lower()):
            return cid
    return None


def auto_pick_personality(
    *,
    requested_id: str,
    llm_model_id: str,
    titles: list[str],
    topic_tags: list[str],
) -> AutoPickResult:
    """
    Hybrid: rules first; if close tie, try LLM to decide among top candidates.
    """
    rid = (requested_id or "").strip().lower()
    if rid and rid != "auto":
        p = get_personality_by_id(rid)
        return AutoPickResult(preset=p, reason="Manual selection")

    scores = _score_rules(titles=titles, topic_tags=topic_tags)
    (a_id, a_score), (b_id, b_score) = _top2(scores)

    # If tie band is small, ask LLM to pick between top candidates.
    tie_band = 1
    chosen_id = a_id
    reason = f"Rules: {a_id} ({a_score})"
    if abs(a_score - b_score) <= tie_band:
        cands = [get_personality_by_id(a_id), get_personality_by_id(b_id)]
        picked = _llm_tiebreak(model_id=llm_model_id, titles=titles, candidates=cands)
        if picked:
            chosen_id = picked
            reason = f"LLM tie-break: {picked} (rules were close)"
        else:
            reason = f"Rules tie: {a_id} ({a_score}) vs {b_id} ({b_score})"

    return AutoPickResult(preset=get_personality_by_id(chosen_id), reason=reason)

