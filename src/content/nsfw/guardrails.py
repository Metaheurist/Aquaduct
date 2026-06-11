"""Adults-only guardrails for the NSFW video format (prompts + topic/crawl filtering)."""

from __future__ import annotations

import os
import re

# Session-only: the desktop app sets this for the current process (title bar F12) to skip LLM guard blocks,
# denylist filtering, NSFW+auto-upload preflight errors, and Tasks upload blocks for explicit renders.
AQUADUCT_DEV_DISABLE_CONTENT_GUARDRAILS = "AQUADUCT_DEV_DISABLE_CONTENT_GUARDRAILS"

# Process gate: F12 session bypass is ignored unless this env is set at startup (dev builds only).
AQUADUCT_DEV_DISABLE_GUARDRAILS = "AQUADUCT_DEV_DISABLE_GUARDRAILS"

# Injected into script / character LLM prompts. Keep explicit and repeatable.
NSFW_ADULTS_ONLY_GUARDRAILS = (
    "NON-NEGOTIABLE CONTENT RULES (18+ ONLY):\n"
    "- All people referenced MUST be consenting adults (21+). No minors, no school framing, no “teen”/underage themes.\n"
    "- No non-consent, coercion, incest, bestiality, or illegal acts. No real public figures or real performer names — invent stage names only.\n"
    "- Scripts are for a private creative pipeline; keep on-screen text, titles, and hashtags professional "
    "(e.g. #adultindustry, #nsfwcreative) — avoid slurs and gratuitous explicit spell-outs in metadata.\n"
    "- Open with a brief spoken disclaimer: adult content, 18+ only, fictional characters.\n"
)

# Patterns for dropping unsafe crawl or topic lines (lowercased match).
NSFW_DENY_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(child|children|minor|minors|underage|preteen|jailbait)\b"),
    re.compile(r"\bteen\b"),
    re.compile(r"\bteenager"),
    re.compile(r"\b(cp|csam)\b"),
    re.compile(r"\b(pedo|pedoph|paedoph)\w*"),
    re.compile(r"\b(loli|shota|lolicon|shotacon)\b"),
    re.compile(r"\b(incest|zoophil|bestialit|beastialit)\w*"),
    re.compile(r"\b(rape|non-?consent|forced\s+sex)\b"),
    re.compile(r"\b(snuff|necrophil)\w*"),
    re.compile(r"\bgang\s*bang\b"),
)


def dev_guardrail_f12_bypass_enabled() -> bool:
    """True when the desktop F12 guardrail bypass is allowed for this process."""
    v = str(os.environ.get(AQUADUCT_DEV_DISABLE_GUARDRAILS, "") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def dev_content_guardrails_disabled() -> bool:
    v = str(os.environ.get(AQUADUCT_DEV_DISABLE_CONTENT_GUARDRAILS, "") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def nsfw_llm_guardrails_block() -> str:
    """Return the LLM guardrail block for NSFW prompts, or empty when session bypass is active."""
    if dev_content_guardrails_disabled():
        return ""
    return NSFW_ADULTS_ONLY_GUARDRAILS


def nsfw_text_matches_denylist(text: str) -> bool:
    """True if ``text`` should be dropped for NSFW sourcing (minors, illegal, etc.)."""
    if dev_content_guardrails_disabled():
        return False
    low = (text or "").lower()
    if not low.strip():
        return False
    return any(p.search(low) for p in NSFW_DENY_REGEXES)
