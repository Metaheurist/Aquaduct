"""
Built-in archetypes for LLM-assisted character generation (Characters tab).

Voice hardware IDs are not generated — the model fills text fields and a boolean
for whether to keep the project default voice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.content.topics import normalize_video_format


@dataclass(frozen=True)
class CharacterAutoPreset:
    """Parameters passed into the script LLM to shape the generated profile."""

    id: str
    label: str
    llm_directive: str
    tags: tuple[str, ...] = ()


@dataclass
class GeneratedCharacterFields:
    name: str
    identity: str
    visual_style: str
    negatives: str
    use_default_voice: bool = True
    gender: str = ""
    ethnicity: str = ""
    age_range: str = ""


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
        CharacterAutoPreset(
            id="nsfw_solo_performer",
            label="NSFW — solo performer host",
            llm_directive=(
                "Confident solo adult entertainer hosting a tasteful vertical short: original stage name, warm-direct camera presence, "
                "consent-positive copy, lingerie-forward or implied-intimacy styling cues — never real people. "
                "Include adults-only guardrails in the character DNA (21+, fictional)."
            ),
            tags=("nsfw",),
        ),
        CharacterAutoPreset(
            id="nsfw_industry_host",
            label="NSFW — industry news host",
            llm_directive=(
                "Adult-industry trade-show host energy: sharp, professional, reads like a presenter at a creators’ conference — "
                "covers trends and studio lore without sleaze in the bio text; original name only; 21+ consenting persona."
            ),
            tags=("nsfw",),
        ),
        CharacterAutoPreset(
            id="nsfw_couple_performers",
            label="NSFW — duo performers",
            llm_directive=(
                "Two original co-host performers (stage names only), consent-positive couple or creative partnership framing, "
                "complementary visual styles, warm banter — adults 21+, no real relationship claims, tasteful wardrobe notes."
            ),
            tags=("nsfw",),
        ),
    ]


def character_auto_presets_for_ui(video_format: str | None = None) -> list[CharacterAutoPreset]:
    """Filter archetypes: NSFW-tagged presets only appear when video format is ``nsfw``."""
    vf = normalize_video_format(video_format or "news")
    out: list[CharacterAutoPreset] = []
    for p in get_character_auto_presets():
        if p.tags and "nsfw" in p.tags and vf != "nsfw":
            continue
        out.append(p)
    return out


def get_character_auto_preset_by_id(pid: str) -> CharacterAutoPreset | None:
    p = (pid or "").strip().lower()
    for x in get_character_auto_presets():
        if x.id == p:
            return x
    return None


def coerce_generated_character_fields(raw: Any) -> GeneratedCharacterFields | None:
    """Normalize LLM JSON dict into :class:`GeneratedCharacterFields`, or ``None`` if unusable."""
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
    gender = str(raw.get("gender", "") or "").strip()
    ethnicity = str(raw.get("ethnicity", "") or "").strip()
    age_range = str(raw.get("age_range", "") or "").strip()
    return GeneratedCharacterFields(
        name=name,
        identity=identity,
        visual_style=visual_style,
        negatives=negatives,
        use_default_voice=udv,
        gender=gender[:256],
        ethnicity=ethnicity[:256],
        age_range=age_range[:256],
    )
