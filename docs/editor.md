# `src/editor.py` — Editor (Micro-clips + captions)

## Purpose
Assemble a final vertical (9:16) MP4 by:
- splitting the video into **few-second micro-clips**
- pairing each micro-clip with one generated image
- overlaying **word-by-word captions**
- optionally applying a **logo watermark**
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

## Optional watermark
If enabled in the UI Branding tab, a logo is overlaid onto each clip during composition:
- position: top-left / top-right / bottom-left / bottom-right / center
- opacity + size are configurable

## Outputs
Per video folder:
- `videos/<title>/final.mp4`
- `videos/<title>/assets/clip_01.mp4` … (intermediate micro-clips)

