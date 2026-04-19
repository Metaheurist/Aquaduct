"""
Built-in archetypes for LLM-assisted character generation (Characters tab).

Voice hardware IDs are not generated — the model fills text fields and a boolean
for whether to keep the project default voice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CharacterAutoPreset:
    """Parameters passed into the script LLM to shape the generated profile."""

    id: str
    label: str
    llm_directive: str


@dataclass
class GeneratedCharacterFields:
    name: str
    identity: str
    visual_style: str
    negatives: str
    use_default_voice: bool = True


def get_character_auto_presets() -> list[CharacterAutoPreset]:
    return [
        CharacterAutoPreset(
            id="unhinged_comedy",
            label="Unhinged comedy",
            llm_directive=(
                "Chaotic satire host: commits to the bit, wrong-foots the audience, "
                "playful cynicism, meme-adjacent punchlines — still kind, no hate or cruelty. "
                "Vertical short-form energy; feels like a fever dream but readable."
            ),
        ),
        CharacterAutoPreset(
            id="gen_z",
            label="Gen Z / chronically online",
            llm_directive=(
                "Gen-Z-coded host: ironic, slang-light (not cringe overload), self-aware, "
                "short attention span friendly, references internet culture abstractly "
                "(no real influencer names). Warm snark."
            ),
        ),
        CharacterAutoPreset(
            id="deadpan_anchor",
            label="Deadpan parody anchor",
            llm_directive=(
                "Fake news desk energy: flat delivery, absurd confidence, tiny blink-and-you-miss-it jokes. "
                "Reads like a parody broadcast, not a real network."
            ),
        ),
        CharacterAutoPreset(
            id="cozy_streamer",
            label="Cozy variety host",
            llm_directive=(
                "Soft-spoken, welcoming, 'come sit by the mic' vibe. Curious questions, gentle humor, "
                "minimal edge. Feels safe and bingeable."
            ),
        ),
        CharacterAutoPreset(
            id="tech_bro_satire",
            label="Tech bro (satire)",
            llm_directive=(
                "Overconfident startup-coded host played for laughs: buzzwords, hustle posture, "
                "but obviously satirical — punch up at ideas, not marginalized groups."
            ),
        ),
        CharacterAutoPreset(
            id="anime_mascot",
            label="Anime mascot energy",
            llm_directive=(
                "Big reactions, expressive host, Saturday-morning pacing without kids' show wholesomeness "
                "unless asked — bold 2D-friendly visuals, original character (not a knockoff of a real show)."
            ),
        ),
        CharacterAutoPreset(
            id="noir_narrator",
            label="Noir / dramatic narrator",
            llm_directive=(
                "Gravelly inner monologue, dramatic lighting metaphors, dry wit. "
                "Feels like a crime doc parody or late-night mystery bumper — not grimdark gore."
            ),
        ),
        CharacterAutoPreset(
            id="elder_millennial",
            label="Elder millennial tired sage",
            llm_directive=(
                "Jaded but kind: remembers the old internet, sighs at new trends, explains with "
                "dad-joke fatigue. Relatable exhaustion, zero punching down."
            ),
        ),
        CharacterAutoPreset(
            id="science_hipster",
            label="Curious science hipster",
            llm_directive=(
                "Enthusiastic nerd host: analogies, wonder, slight hipster aesthetic (labs, plants, vinyl optional). "
                "Clear and friendly, not a dry lecture."
            ),
        ),
        CharacterAutoPreset(
            id="luxury_minimal",
            label="Luxury minimal aesthete",
            llm_directive=(
                "Calm, expensive-sounding minimalism: hushed confidence, clean visuals, "
                "tasteful restraint. Not snobby toward the audience."
            ),
        ),
    ]


def get_character_auto_preset_by_id(pid: str) -> CharacterAutoPreset | None:
    p = (pid or "").strip().lower()
    for x in get_character_auto_presets():
        if x.id == p:
            return x
    return None


def _strip_markdown_fence(text: str) -> str:
    t = (text or "").strip()
    if not t.startswith("```"):
        return t
    lines = t.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_first_json_object(text: str) -> dict[str, Any] | None:
    """Return the first JSON object in *text* (handles leading junk and fenced blocks)."""
    t = _strip_markdown_fence(text)
    dec = json.JSONDecoder()
    i = 0
    while i < len(t):
        if t[i] == "{":
            try:
                obj, _end = dec.raw_decode(t, i)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
        i += 1
    return None


def coerce_generated_character_fields(raw: dict[str, Any] | None) -> GeneratedCharacterFields | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name", "") or "").strip()
    identity = str(raw.get("identity", "") or "").strip()
    visual_style = str(raw.get("visual_style", "") or "").strip()
    negatives = str(raw.get("negatives", "") or "").strip()
    udv = raw.get("use_default_voice", True)
    if isinstance(udv, str):
        udv = udv.strip().lower() in ("1", "true", "yes", "on")
    else:
        udv = bool(udv)
    if not name:
        return None
    if not identity and not visual_style:
        return None
    return GeneratedCharacterFields(
        name=name,
        identity=identity,
        visual_style=visual_style,
        negatives=negatives,
        use_default_voice=udv,
    )
