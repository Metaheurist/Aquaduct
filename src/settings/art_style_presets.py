"""
Curated visual art styles for diffusion: prompt bias + reference strength for img2img continuity.

Used by the Run tab and passed into ``src.render.artist.generate_images``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtStylePreset:
    id: str
    label: str
    #: Prepended to each scene prompt (style cohesion).
    prompt_affix: str
    #: Appended to the negative prompt block (on top of global no-text rules).
    negative_affix: str
    #: Img2img strength when blending from the last up to 3 frames (0.3–0.55 typical).
    reference_strength: float


ART_STYLE_PRESETS: tuple[ArtStylePreset, ...] = (
    ArtStylePreset(
        id="balanced",
        label="Balanced cinematic",
        prompt_affix="cohesive cinematic lighting, consistent color grade across shots, same film look",
        negative_affix="inconsistent lighting, jarring color shift between frames",
        reference_strength=0.42,
    ),
    ArtStylePreset(
        id="neon_tech",
        label="Neon / tech",
        prompt_affix="neon rim light, tech-noir palette, cyan and magenta accents, glossy surfaces, unified glow",
        negative_affix="muted earth tones, flat documentary lighting",
        reference_strength=0.4,
    ),
    ArtStylePreset(
        id="warm_broadcast",
        label="Warm broadcast",
        prompt_affix="warm key light, soft broadcast look, gentle contrast, consistent skin and highlight roll-off",
        negative_affix="cold sterile grading, harsh clipped highlights",
        reference_strength=0.45,
    ),
    ArtStylePreset(
        id="clean_minimal",
        label="Clean minimal 3D",
        prompt_affix="clean minimal 3D render, soft global illumination, matte materials, consistent white balance",
        negative_affix="noisy grain, painterly brush strokes, heavy film grain",
        reference_strength=0.38,
    ),
    ArtStylePreset(
        id="illustration",
        label="Stylized illustration",
        prompt_affix="cohesive illustrated look, same line weight and shading model, unified palette",
        negative_affix="photoreal skin pores, smartphone photo look",
        reference_strength=0.48,
    ),
    ArtStylePreset(
        id="meme_brainrot",
        label="Surreal meme / brainrot",
        prompt_affix=(
            "thick black outlines, flat garish colors, sticker and shitpost meme energy, "
            "wrong perspective, absurd character mashups, crowded comic background, "
            "Italian brainrot chaotic Shorts look, cel-shaded, not photoreal, not sleek corporate sci-fi"
        ),
        negative_affix=(
            "photorealistic, sleek product render, empty abstract neon machinery, stock cyberpunk corridor, "
            "minimalist void, single random futuristic wheel"
        ),
        reference_strength=0.44,
    ),
    ArtStylePreset(
        id="docu_real",
        label="Documentary real",
        prompt_affix="documentary realism, natural light continuity, handheld but stable grade",
        negative_affix="CGI sheen, anime eyes, oversaturated fantasy palette",
        reference_strength=0.35,
    ),
)


def art_style_preset_by_id(preset_id: str | None) -> ArtStylePreset:
    pid = str(preset_id or "").strip()
    for p in ART_STYLE_PRESETS:
        if p.id == pid:
            return p
    return ART_STYLE_PRESETS[0]
