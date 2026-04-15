# `src/utils_ffmpeg.py` — FFmpeg auto-download

## Purpose
Ensure a working `ffmpeg` binary exists without requiring manual installation.

## Behavior
On first run, downloads a Windows FFmpeg build zip and extracts:
- `.cache/ffmpeg/bin/ffmpeg.exe`

Then sets:
- `FFMPEG_BINARY` environment variable

so MoviePy can encode MP4.

## Notes
- Downloads are cached; subsequent runs reuse the existing binary.
- If you already have FFmpeg on PATH, you can still let this run; it will just use the local cached one.

