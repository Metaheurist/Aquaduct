from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import BrandingSettings


@dataclass(frozen=True)
class Fact:
    text: str
    score: float


_PATTERNS = [
    re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"),  # 1,234
    re.compile(r"\b\d+(?:\.\d+)?%\b"),  # 12.5%
    re.compile(r"\$\s*\d+(?:,\d{3})*(?:\.\d+)?\b"),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:billion|million|thousand|B|M|K)\b", re.I),
    re.compile(r"\b(?:top|#\s*)\s*\d{1,3}\b", re.I),
    re.compile(r"\b\d{1,2}\s*x\b", re.I),
    re.compile(r"\b(?:increased|decreased|rose|fell)\s+(?:by\s+)?\d", re.I),
]


def extract_candidate_facts(article_text: str) -> list[Fact]:
    if not (article_text or "").strip():
        return []
    text = " ".join(article_text.split())
    seen: set[str] = set()
    out: list[Fact] = []
    for rx in _PATTERNS:
        for m in rx.finditer(text):
            span = m.group(0).strip()
            if len(span) < 3 or len(span) > 120:
                continue
            key = span.lower()
            if key in seen:
                continue
            seen.add(key)
            # Prefer shorter, punchier facts
            score = 10.0 - min(5.0, len(span) / 40.0)
            if "%" in span or "$" in span:
                score += 2.0
            out.append(Fact(text=span, score=score))
    # Extra: simple "Key number: ..." sentences
    for m in re.finditer(r"([^.!?]{10,120}(?:\d+(?:\.\d+)?%)[^.!?]{0,80})", text):
        chunk = m.group(1).strip()
        if len(chunk) > 180:
            chunk = chunk[:177] + "…"
        k = chunk.lower()
        if k not in seen and len(chunk) >= 12:
            seen.add(k)
            out.append(Fact(text=chunk, score=7.0))
    return sorted(out, key=lambda f: -f.score)


def pick_top_facts(facts: list[Fact], n: int = 2) -> list[str]:
    if not facts:
        return []
    picked: list[str] = []
    for f in facts:
        t = f.text.strip()
        if not t or t in picked:
            continue
        if len(t) > 140:
            t = t[:137] + "…"
        picked.append(t)
        if len(picked) >= n:
            break
    return picked


def _palette(branding: BrandingSettings | None) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    def _hex(s: str, fb: tuple[int, int, int]) -> tuple[int, int, int]:
        s = str(s or "").strip()
        if s.startswith("#"):
            s = s[1:]
        if len(s) != 6:
            return fb
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except Exception:
            return fb

    panel = (18, 18, 22)
    text = (255, 255, 255)
    accent = (37, 244, 238)
    try:
        if branding and bool(getattr(branding, "video_style_enabled", False)):
            from UI.theme import resolve_palette

            pal = resolve_palette(branding)
            text = _hex(pal.get("text", "#FFFFFF"), text)
            accent = _hex(pal.get("accent", "#25F4EE"), accent)
            panel = _hex(pal.get("panel", "#12121A"), panel)
    except Exception:
        pass
    return panel, text, accent


def render_facts_card_rgba(
    *,
    lines: list[str],
    w: int,
    h: int,
    branding: BrandingSettings | None,
    position: str,
) -> np.ndarray:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if not lines:
        return np.array(img)

    panel_rgb, text_rgb, accent_rgb = _palette(branding)
    pad = int(w * 0.06)
    box_w = int(w * 0.42)
    x0 = pad if position != "top_right" else w - pad - box_w
    y0 = pad
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 30)
        body_font = ImageFont.truetype("arial.ttf", 26)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = title_font

    draw = ImageDraw.Draw(img)
    title = "Key facts"
    body_lines = [f"• {ln}" for ln in lines[:2]]
    tw = box_w - 28
    text_block = title + "\n\n" + "\n".join(body_lines)
    # Measure approximate height
    bbox = draw.textbbox((0, 0), text_block, font=body_font)
    bh = bbox[3] - bbox[1] + 50
    bh = min(bh, int(h * 0.22))

    rect = [x0, y0, x0 + box_w, y0 + bh]
    draw.rounded_rectangle(rect, radius=16, fill=(*panel_rgb, 230), outline=(*accent_rgb, 200), width=2)
    tx, ty = x0 + 16, y0 + 12
    draw.text((tx, ty), title, font=title_font, fill=(*text_rgb, 255), stroke_width=2, stroke_fill=(0, 0, 0, 200))
    ty += 36
    for bl in body_lines:
        draw.text((tx, ty), bl, font=body_font, fill=(*text_rgb, 245), stroke_width=2, stroke_fill=(0, 0, 0, 180))
        ty += 32

    return np.array(img)


def facts_visible_until(*, total_dur: float, duration_mode: str) -> float:
    frac = 0.30 if duration_mode == "short" else 0.60
    return max(1.0, float(total_dur) * frac)
