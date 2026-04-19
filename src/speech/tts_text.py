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

