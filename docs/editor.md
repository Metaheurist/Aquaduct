# `src/editor.py` — Editor (Micro-clips + captions)

## Purpose
Assemble a final vertical (9:16) MP4 by:
- splitting the video into **few-second micro-clips**
- pairing each micro-clip with one generated image
- overlaying **word-by-word captions**
- optionally applying a **logo watermark**
- optionally applying the **Key facts** on-screen card (only when **Video format** is **News** or **Explainer**; Cartoon / Unhinged skip it even if enabled in Captions settings)
- concatenating into `final.mp4`

## FFmpeg
MoviePy requires FFmpeg for encoding. The project auto-downloads a Windows build to:
- `.cache/ffmpeg/bin/ffmpeg.exe`

## Micro-clip strategy (MVP)
- Determine `clip_count` from audio duration and available images
- Evenly split the voiceover duration across clips
- For each clip:
  - center-crop image to 9:16
  - subtle zoom
  - render captions into RGBA frames and overlay

## Pillow 10+ and channel matching
- **`src/pillow_compat.py`**: MoviePy’s **`resize`** still references **`PIL.Image.ANTIALIAS`**, removed in Pillow 10+ — a small compat shim runs before importing MoviePy in [`src/editor.py`](../src/editor.py).
- Base **ImageClip** / **VideoFileClip** frames are often **RGB**; caption and facts overlays are **RGBA**. **`CompositeVideoClip`** requires consistent channel counts — **`_ensure_rgba_np`** adds an opaque alpha channel to base and watermark layers before compositing.

## Optional watermark
If enabled in the UI Branding tab, a logo is overlaid onto each clip during composition:
- position: top-left / top-right / bottom-left / bottom-right / center
- opacity + size are configurable

## Outputs
Per video folder:
- `videos/<title>/final.mp4`
- `videos/<title>/assets/clip_01.mp4` … (intermediate micro-clips)

