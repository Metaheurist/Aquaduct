# Editor — Micro-clips, Pro frame sequence, captions

## Purpose
Assemble a final vertical (9:16) MP4 by:
- **Slideshow (default)**: splitting the video into **few-second micro-clips**, pairing each micro-clip with one generated image, optional FFmpeg motion/transitions, then overlaying captions / watermark / facts card.
- **Pro mode (slideshow)**: concatenating **one generated still per output frame** at **`VideoSettings.fps`** for a fixed **`pro_clip_seconds`** timeline, then the same caption / watermark / music composite ([`assemble_pro_frame_sequence_then_concat`](../src/render/editor.py) in [`src/render/editor.py`](../src/render/editor.py)).
- **Clip mode** (`use_image_slideshow=False`): generated video clips from the image model + clip model path ([`assemble_generated_clips_then_concat`](../src/render/editor.py)).

Key facts card: only when **Video format** is **News** or **Explainer**; Cartoon / Unhinged skip it even if enabled in Captions settings.

## FFmpeg
MoviePy requires FFmpeg for encoding. The project auto-downloads a Windows build to:
- `.Aquaduct_data/.cache/ffmpeg/bin/ffmpeg.exe` (see app dirs / `get_paths()`).

## Micro-clip strategy (non–pro slideshow)
- Determine `clip_count` from audio duration and available images
- Evenly split the voiceover duration across clips
- For each clip:
  - center-crop image to target aspect
  - optional subtle zoom (MoviePy path) or FFmpeg motion slideshow
  - render captions into RGBA frames and overlay

## Pro frame sequence
- Frame count: **`round(pro_clip_seconds × fps)`** (cap: **`AQUADUCT_PRO_MAX_FRAMES`**).
- Each image is shown for **`1/fps`** seconds; voice is aligned to **`pro_clip_seconds`** (trim + silence pad) before the final mux.

## Pillow 10+ and channel matching
- **[`src/models/pillow_compat.py`](../src/models/pillow_compat.py)**: MoviePy’s **`resize`** may reference **`PIL.Image.ANTIALIAS`**, removed in Pillow 10+ — compat shim runs before importing MoviePy in [`src/render/editor.py`](../src/render/editor.py).
- Base **ImageClip** / **VideoFileClip** frames are often **RGB**; caption and facts overlays are **RGBA**. **`_ensure_rgba_np`** pads an opaque alpha on base/watermark for consistency. Composites use **`CompositeVideoClip(..., use_bgclip=True)`** so the **first** layer is the full-frame background.

## Optional watermark
If enabled in the UI Branding tab, a logo is overlaid during composition (position, opacity, size).

## Outputs
Per video folder:
- `videos/<title>/final.mp4`
- `videos/<title>/assets/clip_01.mp4` … (intermediate micro-clips when **Export intermediate micro-clips** is on)
