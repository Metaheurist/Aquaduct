# `src/speech/voice.py` — Voice (TTS + captions)

## Purpose
Turn narration text into:
- `voice.wav`
- `captions.json` with **word-level timestamps**

## Kokoro target

### 4. The Speed Demon: Kokoro v1.0

If you don’t have a $2,000 graphics card, this is your model. It is tiny (only **82M** parameters) but sounds shockingly good.

- **Best for:** Real-time applications (like a voice assistant) or running on a laptop/CPU.
- **Key strength:** It is nearly instantaneous. It can generate audio faster than you can read the text.
- **HF Search:** [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)

The app wires **Kokoro-82M** and **MOSS-VoiceGenerator** in [`src/speech/voice.py`](../../src/speech/voice.py) and [`src/speech/tts_kokoro_moss.py`](../../src/speech/tts_kokoro_moss.py). Other Hub rows are still **download-only** until a second engine is added.

### Kokoro-82M (`hexgrad/Kokoro-82M`)
- **Runtime:** `pip install kokoro` (see [hexgrad/kokoro](https://github.com/hexgrad/kokoro)); uses **`KPipeline`** with `lang_code='a'`.
- **Presets (social / narration):** `af_bella`, `af_nicole`, `am_adam` (aliases **Bella**, **Nicole**, **Adam** in the Characters form).
- **Shuffle:** if the per-character **Kokoro speaker** field is **empty**, each run picks **one** preset at random. **Unhinged** format (hook / segments / CTA) with default project voice **rotates** `af_bella` → `af_nicole` → `am_adam` per segment. If the user sets a speaker id, that id is used for the whole read (or every segment in unhinged).
- If Kokoro isn’t installed or fails, the pipeline uses **pyttsx3** (same as before).

### MOSS-VoiceGenerator (`OpenMOSS-Team/MOSS-VoiceGenerator`)
- **Instruction + text:** you describe the voice in natural language, and the model reads the script (no reference clip). Implementation follows the [model card](https://huggingface.co/OpenMOSS-Team/MOSS-VoiceGenerator) (`transformers` + `trust_remote_code=True`). Needs a **strong GPU** and recent dependencies; on failure, **pyttsx3** is used.
- **Run tab → Personality** is merged into the MOSS *instruction* (delivery tone) via `merge_moss_character_and_run_personality` in [`src/speech/tts_text.py`](../../src/speech/tts_text.py), after the effective personality is chosen (including **Auto**).
- **Characters → Voice instruction:** optional extra free-form line (e.g. timbre). It is **prepended** to the Run-personality line for MOSS. If only Personality is set, that alone drives the style instruction. If both are empty, the pipeline uses the default narrator instruction.
- **Kokoro / pyttsx3 / ElevenLabs:** do not read the MOSS instruction; they use the **shaped** narration from `shape_tts_text` with the same **Personality** id (line breaks, chunk length).
- **Unhinged:** each spoken segment is synthesized with the **same** instruction, then audio is concatenated.

**Settings → Model → Voice** only lists **Kokoro-82M** and **MOSS-VoiceGenerator** for local snapshot **download**; the pipeline runs Kokoro, MOSS, or `pyttsx3` for speech.

## Retry ladder (local transformers path)
Heavy local voice loads are wrapped in **`retry_stage`** ([`main.py`](../../main.py)): failures can downgrade **MOSS → Kokoro** per [`variant_fallback`](../../src/runtime/variant_fallback.py), and curated mappings include a **`aquaduct/system-tts-pyttsx3`** sentinel id mapped to **`pyttsx3`**-only synthesis when GPUs or wheels cannot run MOSS/Kokoro. **ElevenLabs** remains a separate HTTP API path — not the same transformer retry loop.

## Offline fallback (always runnable)
If Kokoro generation is unavailable, the MVP falls back to:
- `pyttsx3` (Windows SAPI)

## ElevenLabs (optional cloud TTS)
When enabled in **API** and the active **character** selects an ElevenLabs voice, narration can be synthesized via the ElevenLabs HTTP API (`requests`); audio is converted to WAV with FFmpeg for the rest of the pipeline. On API failure or missing key, the pipeline falls back to the selected local voice model (Kokoro or MOSS) and then `pyttsx3`. See [ElevenLabs setup](../integrations/elevenlabs.md) and [Characters](../ui/characters.md).

## Caption timing (MVP)
Word timestamps are estimated by distributing total audio duration across words with slight weighting by word length. This is fast and avoids ASR/forced-alignment.

## Outputs
Written into the per-video folder:
- `videos/<title>/assets/voice.wav`
- `videos/<title>/assets/captions.json`

