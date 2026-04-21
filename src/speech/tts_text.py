from __future__ import annotations

import re

from src.content.personalities import get_personality_by_id


def _sentences(text: str) -> list[str]:
    t = " ".join((text or "").split()).strip()
    if not t:
        return []
    # Basic sentence split on . ! ? with keep
    parts = re.split(r"([.!?])", t)
    out: list[str] = []
    cur = ""
    for p in parts:
        if p in (".", "!", "?"):
            cur = (cur + p).strip()
            if cur:
                out.append(cur)
            cur = ""
        else:
            cur += " " + p
    cur = cur.strip()
    if cur:
        out.append(cur)
    return out


def shape_tts_text(text: str, *, personality_id: str = "neutral") -> str:
    """
    Deterministic text shaping for nicer offline TTS:
    - sentence chunking
    - punctuation tuning for pauses/emphasis
    - personality-specific pacing (urgent: shorter chunks)
    """
    sents = _sentences(text)
    if not sents:
        return ""

    pid = (personality_id or "neutral").strip().lower()
    preset = get_personality_by_id(pid)
    override = getattr(preset, "tts_max_chunk_words", None)
    if isinstance(override, int) and override > 0:
        max_words = override
    else:
        max_words = 16
        if pid in ("urgent", "hype"):
            max_words = 12
        elif pid in ("analytical",):
            max_words = 18

    out: list[str] = []
    for s in sents:
        s = s.strip()
        # Add emphasis pauses for common patterns
        s = re.sub(r"\bbut\b", "—but", s, flags=re.IGNORECASE)
        s = re.sub(r"\bso\b", "—so", s, flags=re.IGNORECASE)

        words = [w for w in s.split(" ") if w]
        if len(words) <= max_words:
            out.append(s)
            continue

        # Chunk long sentences into shorter ones.
        chunk: list[str] = []
        for w in words:
            chunk.append(w)
            if len(chunk) >= max_words:
                out.append(" ".join(chunk).rstrip(",") + "…")
                chunk = []
        if chunk:
            out.append(" ".join(chunk))

    # Newlines create audible pauses in many engines (including pyttsx3/SAPI).
    shaped = "\n".join(out).strip()
    return shaped


_MAX_MOSS_PERSONALITY_INSTRUCTION_CHARS = 1200


def moss_style_instruction_for_personality(personality_id: str) -> str:
    """
    Build a short natural-language style line for **MOSS-VoiceGenerator** (instruction channel)
    from the Run tab **Personality** preset. Used together with character voice instruction when set.
    """
    p = get_personality_by_id((personality_id or "neutral").strip().lower())
    parts = [f"Narration delivery: {p.label}. {p.description}"]
    if p.style_rules:
        parts.append(" ".join(p.style_rules[:2]))
    out = " ".join(parts).strip()
    if len(out) > _MAX_MOSS_PERSONALITY_INSTRUCTION_CHARS:
        return out[:_MAX_MOSS_PERSONALITY_INSTRUCTION_CHARS].rsplit(" ", 1)[0] + "…"
    return out


def merge_moss_character_and_run_personality(
    character_voice_instruction: str | None,
    run_personality_id: str,
) -> str | None:
    """
    MOSS: combine optional **Character → Voice instruction** with Run tab **Personality** tone.
    If only personality is set, return that style string (so MOSS is never instruction-free when personality is known).
    """
    c = (character_voice_instruction or "").strip()
    ptxt = moss_style_instruction_for_personality(run_personality_id)
    if c and ptxt:
        return f"{c}\n\n[Run personality — voice tone]\n{ptxt}"
    if c:
        return c
    if ptxt:
        return ptxt
    return None

