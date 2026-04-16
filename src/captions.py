from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import BrandingSettings, VideoSettings


@dataclass(frozen=True)
class CaptionWord:
    word: str
    start: float
    end: float


def load_captions_json(captions_json: Path) -> list[CaptionWord]:
    data = json.loads(captions_json.read_text(encoding="utf-8"))
    out: list[CaptionWord] = []
    if isinstance(data, list):
        for w in data:
            if not isinstance(w, dict):
                continue
            word = str(w.get("word", "")).strip()
            try:
                start = float(w.get("start", 0.0))
                end = float(w.get("end", 0.0))
            except Exception:
                continue
            if word and end > start:
                out.append(CaptionWord(word=word, start=start, end=end))
    return out


def caption_window_for_time(words: list[CaptionWord], t: float, max_words: int) -> tuple[list[str], list[int], int]:
    """
    Rolling window of up to `max_words` words that have started by time `t`,
    plus active index within the window (-1 if none).
    """
    if not words:
        return [], [], -1
    max_words = max(3, min(12, int(max_words)))
    active_global = -1
    for i, w in enumerate(words):
        if w.start <= t <= w.end:
            active_global = i
            break
    started = [i for i, w in enumerate(words) if w.start <= t + 0.02]
    if not started:
        return [], [], -1
    hi = started[-1]
    lo = max(0, hi - max_words + 1)
    idxs = list(range(lo, hi + 1))
    strings = [words[i].word for i in idxs]
    active_in_window = -1
    if active_global >= 0 and active_global in idxs:
        active_in_window = idxs.index(active_global)
    return strings, idxs, active_in_window


_NUM_RE = re.compile(r"^[\d.,%$€£]+$|^\d+%$|^\$\d|^\d+\s*(x|×|times)\b", re.I)


def _is_number_token(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if _NUM_RE.search(s):
        return True
    return bool(re.search(r"\d", s))


def _is_keyword_token(s: str, topic_tags: list[str]) -> bool:
    low = s.lower().strip(".,!?;:\"'")
    for tag in topic_tags:
        t = tag.lower().strip()
        if len(t) >= 3 and t in low:
            return True
    if len(s) >= 4 and s[:1].isupper() and s[1:].islower():
        return True
    return False


def _resolve_palette_colors(branding: BrandingSettings | None) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    text_rgb = (255, 255, 255)
    accent_rgb = (0, 255, 200)
    stroke_rgb = (0, 0, 0)

    def _hex_to_rgb(s: str, fb: tuple[int, int, int]) -> tuple[int, int, int]:
        s = str(s or "").strip()
        if s.startswith("#"):
            s = s[1:]
        if len(s) != 6:
            return fb
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except Exception:
            return fb

    try:
        if branding and bool(getattr(branding, "video_style_enabled", False)):
            from UI.theme import resolve_palette

            pal = resolve_palette(branding)
            text_rgb = _hex_to_rgb(pal.get("text", "#FFFFFF"), text_rgb)
            accent_rgb = _hex_to_rgb(pal.get("accent", "#25F4EE"), accent_rgb)
    except Exception:
        pass
    return text_rgb, accent_rgb, stroke_rgb


def _pick_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arialbd.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("arial.ttf", size)
        except Exception:
            return ImageFont.load_default()


def _wrap_words_to_lines(word_strings: list[str], font: ImageFont.FreeTypeFont | ImageFont.ImageFont, draw: ImageDraw.ImageDraw, max_width: int) -> list[list[str]]:
    if not word_strings:
        return []
    lines: list[list[str]] = []
    cur: list[str] = []
    for w in word_strings:
        test_words = cur + [w]
        test = " ".join(test_words)
        bbox = draw.textbbox((0, 0), test, font=font)
        tw = bbox[2] - bbox[0]
        if tw <= max_width or not cur:
            cur.append(w)
            continue
        lines.append(cur)
        cur = [w]
    if cur:
        lines.append(cur)
    return lines


def render_caption_overlay_rgba(
    *,
    word_strings: list[str],
    window_indices: list[int],
    active_in_window: int,
    all_words: list[CaptionWord],
    w: int,
    h: int,
    branding: BrandingSettings | None,
    settings: VideoSettings,
    topic_tags: list[str],
) -> np.ndarray:
    """
    Word-accurate caption overlay: wrapped lines, dynamic font size, stroke/shadow,
    rounded highlight behind active word, emphasis for numbers/keywords.
    """
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if not bool(getattr(settings, "captions_enabled", True)):
        return np.array(img)

    if not word_strings:
        return np.array(img)

    text_rgb, accent_rgb, stroke_rgb = _resolve_palette_colors(branding)
    intensity = str(getattr(settings, "caption_highlight_intensity", "strong") or "strong")
    subtle = intensity == "subtle"
    margin_x = int(w * 0.09)
    box_w = w - 2 * margin_x
    y0 = int(h * 0.64)

    font_size = 56
    min_size = 22
    lines: list[list[str]] = []
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont = _pick_font(font_size)

    while font_size >= min_size:
        font = _pick_font(font_size)
        draw = ImageDraw.Draw(img)
        lines = _wrap_words_to_lines(word_strings, font, draw, box_w)
        if len(lines) <= 2 and lines:
            # check total height
            line_h = max(
                draw.textbbox((0, 0), "Ay", font=font)[3] - draw.textbbox((0, 0), "Ay", font=font)[1],
                12,
            )
            if len(lines) * (line_h + 8) <= int(h * 0.28):
                break
        font_size -= 2

    if len(lines) > 2:
        tail: list[str] = []
        for ln in lines[2:]:
            tail.extend(ln)
        lines = [lines[0], lines[1] + tail] if len(lines) >= 2 else [lines[0] + tail]

    draw = ImageDraw.Draw(img)
    line_h = max(
        draw.textbbox((0, 0), "Ay", font=font)[3] - draw.textbbox((0, 0), "Ay", font=font)[1],
        12,
    )

    line_strs = [" ".join(ln) for ln in lines]
    line_dims: list[tuple[int, int]] = []
    for ls in line_strs:
        bb = draw.textbbox((0, 0), ls, font=font)
        line_dims.append((bb[2] - bb[0], bb[3] - bb[1]))

    word_boxes: list[tuple[int, int, int, int]] = []
    wp = 0
    for li, line in enumerate(lines):
        lw, _lh = line_dims[li]
        x_start = (w - lw) // 2
        x_cursor = x_start
        y_line = y0 + li * (line_h + 10)
        for ci, tok in enumerate(line):
            if ci > 0:
                sp = draw.textbbox((0, 0), " ", font=font)
                x_cursor += sp[2] - sp[0]
            bb = draw.textbbox((0, 0), tok, font=font)
            tw = bb[2] - bb[0]
            th = bb[3] - bb[1]
            pad = 4
            word_boxes.append((x_cursor - pad, y_line - pad, x_cursor + tw + pad, y_line + th + pad))
            x_cursor += tw
            wp += 1

    # Highlight active (requires bbox alignment with window tokens)
    can_hl = len(word_boxes) == len(word_strings)
    if can_hl and 0 <= active_in_window < len(word_boxes) and not subtle:
        x0b, y0b, x1b, y1b = word_boxes[active_in_window]
        draw.rounded_rectangle(
            [x0b, y0b, x1b, y1b],
            radius=10,
            fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 110),
            outline=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 160),
            width=2,
        )
    elif can_hl and 0 <= active_in_window < len(word_boxes) and subtle:
        x0b, y0b, x1b, y1b = word_boxes[active_in_window]
        draw.rounded_rectangle(
            [x0b, y0b, x1b, y1b],
            radius=8,
            fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 55),
            outline=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 90),
            width=1,
        )

    shadow_off = 3
    win_pos = 0
    kw_used_per_line: dict[int, int] = {}
    for li, line in enumerate(lines):
        lw, _ = line_dims[li]
        x_start = (w - lw) // 2
        x_cursor = x_start
        y_line = y0 + li * (line_h + 10)
        for _ci, tok in enumerate(line):
            if _ci > 0:
                sp = draw.textbbox((0, 0), " ", font=font)
                x_cursor += sp[2] - sp[0]
            is_active = win_pos == active_in_window
            wi = window_indices[win_pos] if win_pos < len(window_indices) else -1
            orig = all_words[wi].word if 0 <= wi < len(all_words) else tok
            num_em = _is_number_token(orig)
            kw_em = _is_keyword_token(orig, topic_tags) and not num_em
            used = kw_used_per_line.get(li, 0)
            if kw_em and not is_active and used >= 2:
                kw_em = False
            if kw_em and not is_active:
                kw_used_per_line[li] = used + 1
            fill: tuple[int, int, int, int]
            if is_active or num_em:
                fill = (*accent_rgb, 255)
            elif kw_em:
                fill = (accent_rgb[0], accent_rgb[1], accent_rgb[2], 230)
            else:
                fill = (*text_rgb, 235)
            sw = 6 if num_em else 4
            draw.text(
                (x_cursor + shadow_off, y_line + shadow_off),
                tok,
                font=font,
                fill=(0, 0, 0, 160),
            )
            draw.text(
                (x_cursor, y_line),
                tok,
                font=font,
                fill=fill,
                stroke_width=sw,
                stroke_fill=(*stroke_rgb, 240),
            )
            bb = draw.textbbox((0, 0), tok, font=font)
            x_cursor += bb[2] - bb[0]
            win_pos += 1

    return np.array(img)


def transparent_frame(w: int, h: int) -> np.ndarray:
    return np.zeros((h, w, 4), dtype=np.uint8)
