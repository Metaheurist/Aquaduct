# Branding

The **Branding** tab lets you customize the app theme and optionally add logo watermarks (video mode) or photo layout styling (photo mode).

## Layout

1. **Theme** — palette presets and per-color overrides (shown first).
2. **Video look** — optional video style strength (video mode only; whole section hidden in Photo mode).
3. **Photo layouts** — frame and paper tint (photo mode only).
4. **Logo watermark** — path, position, opacity, size (video mode only).

Each mode-specific block lives in its own section container so **Photo | Video** toggling hides labels and controls together ([`MainWindow._apply_media_mode_ui`](../../UI/main_window.py)).

## Theme (optional)

- Enable **“Enable theme overrides”** to apply a custom palette.
- Choose a **preset palette** (see `PRESET_PALETTES` in [`UI/theme/palette.py`](../../UI/theme/palette.py)) or **Custom**.
- When you pick a **named preset** (not Custom), the **Theme color** rows update to that preset’s canonical colors. Per-row override checkboxes keep saved colors on load when checked.
- **Hex input + Pick…** for each color row. Invalid hex values fall back safely.

## Logo watermark (videos)

- Enable **“Watermark generated videos with a logo”**
- **Browse…** to select `.png` / `.jpg` / `.webp`
- Configure position, opacity, and size (fraction of video width)

If watermarking is enabled but the path is invalid, **preflight fails** before Run.

## Video style (palette → prompts + captions)

When enabled, the Branding palette influences generated video prompts and caption accent colors.

- **Subtle** — readability first.
- **Strong** — more dominant palette in prompts.

## Photo layouts (photo mode)

Optional frame border width and paper tint for poster / newspaper / comic outputs.

See [Desktop UI overview](ui.md) and [shared widgets](shared-widgets.md).
