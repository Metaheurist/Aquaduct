# Branding (theme + logo watermark)

The **Branding** tab lets you customize the app’s look and optionally add a logo watermark to generated videos.

## Theme (optional)
- Enable **“Enable theme overrides”** to apply a custom palette.
- Choose a **preset palette** (e.g. Default, Ocean, Sunset, Monochrome, Amber night, Dracula, Ember, Forest, Lavender, Nord night, Rose, Slate — see `PRESET_PALETTES` in [`UI/theme/palette.py`](../../UI/theme/palette.py)) or **Custom**.
- When you pick a **named preset** (not Custom), the **Theme color** rows below update to that preset’s canonical colors (hex + swatches). If you had **per-row overrides** checked, those rows keep their saved colors on load; changing the palette again applies the full preset to every row.
- If you select **Custom**, each color override has its own checkbox:
  - Background
  - Panel
  - Text
  - Muted text
  - Accent
  - Danger

### Hex input + color picker
- You can type a hex color like `#25F4EE`.
- Or click **Pick…** to choose a color and auto-fill the hex value.

Invalid hex values are ignored and safely fall back to the selected preset.

## Logo watermark (videos)
- Enable **“Watermark generated videos with a logo”**
- Select an image file (`.png`, `.jpg`, `.webp`)
- Configure:
  - position
  - opacity
  - size (as a fraction of video width)

### Validation
If watermarking is enabled but the file path is missing/invalid, **preflight will fail** (strict mode blocks runs) so you don’t start a run that can’t complete.

## Video style (palette → prompts + captions)
If enabled, the Branding palette also influences the generated video:

- **Prompts**: the palette is appended to each segment’s `visual_prompt` so image/video generation trends toward the same vibe.
- **Captions**: the caption highlight bar uses the palette accent color; text remains high-contrast for readability.

### Strength
- **Subtle**: small accent usage; keep the original “cyberpunk UI” look, just nudged toward the palette.
- **Strong**: more dominant palette language in prompts so visuals lean heavily toward the selected colors.

