from __future__ import annotations

from pathlib import Path
from typing import Literal


PictureFormat = Literal["poster", "newspaper", "comic"]


def _fit_cover(im, size: tuple[int, int]):
    from PIL import Image

    w, h = size
    iw, ih = im.size
    if iw <= 0 or ih <= 0:
        return im.resize((w, h))
    scale = max(w / float(iw), h / float(ih))
    nw, nh = int(round(iw * scale)), int(round(ih * scale))
    im2 = im.resize((nw, nh), Image.Resampling.LANCZOS)
    x0 = max(0, (nw - w) // 2)
    y0 = max(0, (nh - h) // 2)
    return im2.crop((x0, y0, x0 + w, y0 + h))


def render_layout(
    *,
    picture_format: str,
    images: list[Path],
    title: str,
    out_path: Path,
    size: tuple[int, int] = (1080, 1920),
    branding=None,
) -> Path:
    """
    Minimal v1 layout renderer for Photo mode.

    - poster: hero image + title strip
    - newspaper: masthead + 2-column grid of images
    - comic: 2x3 grid panels
    """
    from PIL import Image, ImageDraw, ImageFont

    fmt: PictureFormat = "poster"
    pf = str(picture_format or "poster").strip().lower()
    if pf in ("poster", "newspaper", "comic"):
        fmt = pf  # type: ignore[assignment]

    w, h = int(size[0]), int(size[1])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bg = (12, 12, 16)
    frame_on = False
    frame_w = 24
    try:
        if branding is not None and bool(getattr(branding, "photo_style_enabled", False)):
            hx = str(getattr(branding, "photo_paper_hex", "#F2F0E9") or "#F2F0E9").strip()
            if hx.startswith("#") and len(hx) == 7:
                bg = tuple(int(hx[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[assignment]
            frame_on = bool(getattr(branding, "photo_frame_enabled", False))
            frame_w = int(getattr(branding, "photo_frame_width", 24) or 24)
    except Exception:
        bg = (12, 12, 16)
        frame_on = False
        frame_w = 24

    canvas = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(canvas)

    # Font best-effort
    try:
        font_big = ImageFont.truetype("arial.ttf", 56)
        font_med = ImageFont.truetype("arial.ttf", 34)
    except Exception:
        font_big = ImageFont.load_default()
        font_med = ImageFont.load_default()

    imgs: list[Image.Image] = []
    for p in images[:12]:
        try:
            imgs.append(Image.open(p).convert("RGB"))
        except Exception:
            continue
    if not imgs:
        canvas.save(out_path)
        return out_path

    if fmt == "poster":
        hero_h = int(round(h * 0.82))
        hero = _fit_cover(imgs[0], (w, hero_h))
        canvas.paste(hero, (0, 0))
        # Title strip
        strip_h = h - hero_h
        draw.rectangle([0, hero_h, w, h], fill=(8, 8, 12))
        t = (title or "").strip() or "Poster"
        draw.text((34, hero_h + 18), t[:80], fill=(245, 245, 250), font=font_big)
    elif fmt == "newspaper":
        mast_h = int(round(h * 0.14))
        draw.rectangle([0, 0, w, mast_h], fill=(235, 235, 238))
        mast = (title or "").strip() or "THE AQUADUCT TIMES"
        draw.text((26, 22), mast[:80], fill=(20, 20, 26), font=font_big)
        # 2 columns of images below
        pad = 18
        grid_top = mast_h + pad
        col_w = (w - pad * 3) // 2
        row_h = (h - grid_top - pad * 3) // 3
        k = 0
        for r in range(3):
            for c in range(2):
                if k >= len(imgs):
                    break
                x = pad + c * (col_w + pad)
                y = grid_top + r * (row_h + pad)
                tile = _fit_cover(imgs[k], (col_w, row_h))
                canvas.paste(tile, (x, y))
                k += 1
    else:
        # comic: 2x3
        pad = 18
        cols, rows = 2, 3
        panel_w = (w - pad * (cols + 1)) // cols
        panel_h = (h - pad * (rows + 1)) // rows
        k = 0
        for r in range(rows):
            for c in range(cols):
                x = pad + c * (panel_w + pad)
                y = pad + r * (panel_h + pad)
                if k < len(imgs):
                    panel = _fit_cover(imgs[k], (panel_w, panel_h))
                    canvas.paste(panel, (x, y))
                draw.rectangle([x, y, x + panel_w, y + panel_h], outline=(10, 10, 14), width=6)
                k += 1

        # small title in corner
        t = (title or "").strip()
        if t:
            draw.rectangle([0, 0, w, 86], fill=(12, 12, 16))
            draw.text((20, 20), t[:60], fill=(245, 245, 250), font=font_med)

    canvas.save(out_path)
    if frame_on and frame_w > 0:
        try:
            # draw a simple border frame on top
            im = Image.open(out_path).convert("RGB")
            d2 = ImageDraw.Draw(im)
            fw = max(2, min(int(frame_w), min(w, h) // 6))
            d2.rectangle([fw // 2, fw // 2, w - fw // 2, h - fw // 2], outline=(10, 10, 14), width=fw)
            im.save(out_path)
        except Exception:
            pass
    return out_path

