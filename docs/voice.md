# `src/voice.py` — Voice (TTS + captions)

## Purpose
Turn narration text into:
- `voice.wav`
- `captions.json` with **word-level timestamps**

## Kokoro target
The project is designed to use the **Kokoro-82M** model locally. Packaging/APIs can vary, so the MVP keeps a best-effort stub and stays runnable even if Kokoro integration isn’t available yet.

## Offline fallback (always runnable)
If Kokoro generation is unavailable, the MVP falls back to:
- `pyttsx3` (Windows SAPI)

## Caption timing (MVP)
Word timestamps are estimated by distributing total audio duration across words with slight weighting by word length. This is fast and avoids ASR/forced-alignment.

## Outputs
Written into the per-video folder:
- `videos/<title>/assets/voice.wav`
- `videos/<title>/assets/captions.json`

