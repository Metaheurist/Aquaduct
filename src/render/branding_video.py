from __future__ import annotations

from typing import Literal

from src.core.config import BrandingSettings


def _is_enabled(branding: BrandingSettings | None) -> bool:
    return bool(branding) and bool(getattr(branding, "video_style_enabled", False))


def video_style_strength(branding: BrandingSettings | None) -> Literal["subtle", "strong"]:
    s = str(getattr(branding, "video_style_strength", "subtle") or "subtle").strip().lower()
    return "strong" if s == "strong" else "subtle"


def palette_prompt_suffix(branding: BrandingSettings | None) -> str:
    """
    Returns a short suffix that nudges image/video generation toward the UI palette.
    """
    if not _is_enabled(branding):
        return ""

    # Import lazily to avoid UI import overhead unless needed (UI/theme.py is safe: no Qt imports).
    from UI.theme import resolve_palette

    pal = resolve_palette(branding)
    accent = pal.get("accent", "#25F4EE")
    danger = pal.get("danger", "#FE2C55")
    bg = pal.get("bg", "#0F0F10")
    strength = video_style_strength(branding)

    if strength == "strong":
        return (
            f"Palette: dominant accents {accent} and {danger}, deep dark base {bg}, "
            "high contrast, neon UI overlays, cinematic lighting"
        )
    return f"Palette: subtle accents {accent}, deep dark base {bg}, clean high contrast, minimal neon"


def apply_palette_to_prompt(prompt: str, branding: BrandingSettings | None) -> str:
    """
    Appends palette suffix to a prompt (idempotent).
    """
    p = str(prompt or "").strip()
    suf = palette_prompt_suffix(branding)
    if not p or not suf:
        return p
    # Idempotent marker
    if "Palette:" in p:
        return p
    return f"{p}, {suf}"


def apply_palette_to_prompts(prompts: list[str], branding: BrandingSettings | None) -> list[str]:
    return [apply_palette_to_prompt(p, branding) for p in (prompts or [])]

