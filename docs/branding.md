# Branding (theme + logo watermark)

The **Branding** tab lets you customize the app’s look and optionally add a logo watermark to generated videos.

## Theme (optional)
- Enable **“Enable theme overrides”** to apply a custom palette.
- Choose a **preset palette** (Default/Ocean/Sunset/Mono) or **Custom**.
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

