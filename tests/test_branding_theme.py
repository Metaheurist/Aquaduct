from __future__ import annotations

from src.config import BrandingSettings
from UI.theme import build_qss, resolve_palette


def test_resolve_palette_invalid_hex_falls_back():
    b = BrandingSettings(
        theme_enabled=True,
        palette_id="ocean",
        accent_enabled=True,
        accent_hex="not-a-hex",
    )
    pal = resolve_palette(b)
    # Ocean preset accent should win because invalid override is rejected.
    assert pal["accent"] == "#2BE6FF"


def test_resolve_palette_normalizes_hex_uppercase():
    b = BrandingSettings(
        theme_enabled=True,
        palette_id="default",
        accent_enabled=True,
        accent_hex="25f4ee",
    )
    pal = resolve_palette(b)
    assert pal["accent"] == "#25F4EE"


def test_build_qss_includes_palette_values():
    pal = resolve_palette(None)
    qss = build_qss(pal)
    assert pal["bg"] in qss
    assert pal["accent"] in qss

