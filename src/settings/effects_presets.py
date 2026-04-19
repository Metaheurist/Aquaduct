"""
Curated effect / audio templates for the Effects tab.

Each preset sets motion, transitions, retries, seed, and audio-mix fields.
Changing any control below the tiles switches selection to **Custom**.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EffectsPreset:
    id: str
    title: str
    #: Second line on the tile (compact summary)
    subtitle: str
    #: Longer description for tooltips
    description: str
    quality_retries: int
    enable_motion: bool
    transition_strength: str  # off | low | med
    xfade_transition: str
    seed_base: int | None
    audio_polish: str  # off | basic | strong
    music_ducking: bool
    music_ducking_amount: float
    music_fade_s: float
    sfx_mode: str  # off | subtle


EFFECT_PRESETS: tuple[EffectsPreset, ...] = (
    EffectsPreset(
        id="effects_minimal",
        title="Minimal (fast)",
        subtitle="No crossfades · 0 retries · light audio",
        description="Fastest encode: transitions off, no quality retries, basic audio polish.",
        quality_retries=0,
        enable_motion=True,
        transition_strength="off",
        xfade_transition="fade",
        seed_base=None,
        audio_polish="basic",
        music_ducking=True,
        music_ducking_amount=0.55,
        music_fade_s=0.8,
        sfx_mode="off",
    ),
    EffectsPreset(
        id="effects_balanced",
        title="Balanced (default)",
        subtitle="Motion · soft fades · basic mix",
        description="Matches app defaults: light crossfades, standard retries, balanced ducking.",
        quality_retries=2,
        enable_motion=True,
        transition_strength="low",
        xfade_transition="fade",
        seed_base=None,
        audio_polish="basic",
        music_ducking=True,
        music_ducking_amount=0.7,
        music_fade_s=1.2,
        sfx_mode="off",
    ),
    EffectsPreset(
        id="effects_polished",
        title="Polished slideshow",
        subtitle="Dissolve · basic audio",
        description="Slightly richer transitions with dissolve; same balanced audio.",
        quality_retries=2,
        enable_motion=True,
        transition_strength="low",
        xfade_transition="dissolve",
        seed_base=None,
        audio_polish="basic",
        music_ducking=True,
        music_ducking_amount=0.72,
        music_fade_s=1.4,
        sfx_mode="off",
    ),
    EffectsPreset(
        id="effects_dynamic",
        title="Dynamic cuts",
        subtitle="Medium wipes · subtle SFX",
        description="Stronger transition duration with directional movement; optional whoosh layer.",
        quality_retries=2,
        enable_motion=True,
        transition_strength="med",
        xfade_transition="slideleft",
        seed_base=None,
        audio_polish="basic",
        music_ducking=True,
        music_ducking_amount=0.68,
        music_fade_s=1.2,
        sfx_mode="subtle",
    ),
    EffectsPreset(
        id="effects_cinematic",
        title="Cinematic",
        subtitle="Smooth pan · strong audio",
        description="Heavier motion crossfades and stronger FFmpeg audio polish for a trailer feel.",
        quality_retries=3,
        enable_motion=True,
        transition_strength="med",
        xfade_transition="smoothleft",
        seed_base=None,
        audio_polish="strong",
        music_ducking=True,
        music_ducking_amount=0.78,
        music_fade_s=2.0,
        sfx_mode="subtle",
    ),
    EffectsPreset(
        id="effects_voice_first",
        title="Voice-first",
        subtitle="Heavy ducking · clear VO",
        description="Prioritizes narration: stronger ducking, shorter music fades.",
        quality_retries=2,
        enable_motion=True,
        transition_strength="low",
        xfade_transition="fade",
        seed_base=None,
        audio_polish="basic",
        music_ducking=True,
        music_ducking_amount=0.88,
        music_fade_s=0.9,
        sfx_mode="off",
    ),
    EffectsPreset(
        id="effects_music_forward",
        title="Music-forward",
        subtitle="Gentle ducking · long fades",
        description="Keeps bed music more audible; lighter ducking and longer crossfades at boundaries.",
        quality_retries=2,
        enable_motion=True,
        transition_strength="low",
        xfade_transition="fade",
        seed_base=None,
        audio_polish="basic",
        music_ducking=True,
        music_ducking_amount=0.42,
        music_fade_s=2.6,
        sfx_mode="subtle",
    ),
)


def preset_by_id(preset_id: str) -> EffectsPreset | None:
    pid = str(preset_id or "").strip()
    if not pid:
        return None
    for p in EFFECT_PRESETS:
        if p.id == pid:
            return p
    return None


def find_best_preset_for_effects(
    *,
    quality_retries: int,
    enable_motion: bool,
    transition_strength: str,
    xfade_transition: str,
    seed_base: int | None,
    audio_polish: str,
    music_ducking: bool,
    music_ducking_amount: float,
    music_fade_s: float,
    sfx_mode: str,
) -> str:
    """If current values match a template, return its id; else empty string (Custom)."""
    ts = str(transition_strength or "low")
    if ts not in ("off", "low", "med"):
        ts = "low"
    ap = str(audio_polish or "basic")
    if ap not in ("off", "basic", "strong"):
        ap = "basic"
    sfx = str(sfx_mode or "off")
    if sfx not in ("off", "subtle"):
        sfx = "off"
    xf = str(xfade_transition or "fade")

    for p in EFFECT_PRESETS:
        if p.quality_retries != int(quality_retries):
            continue
        if p.enable_motion != bool(enable_motion):
            continue
        if p.transition_strength != ts:
            continue
        if p.xfade_transition != xf:
            continue
        if p.seed_base != seed_base:
            continue
        if p.audio_polish != ap:
            continue
        if p.music_ducking != bool(music_ducking):
            continue
        if abs(float(p.music_ducking_amount) - float(music_ducking_amount)) > 0.02:
            continue
        if abs(float(p.music_fade_s) - float(music_fade_s)) > 0.06:
            continue
        if p.sfx_mode != sfx:
            continue
        return p.id
    return ""
