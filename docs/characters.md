# Characters (Character Builder)

User-defined **characters** store a host identity, optional diffusion visual style and negatives, and optional narration voice overrides. They are saved in `data/characters.json` under the project root.

## Fields

- **Name** — list label and script context.
- **Identity / persona** — fed to the LLM as extra context so narration and on-screen text stay consistent with the chosen **Personality** preset on the Run tab (personality controls tone; character adds who-the-host-is).
- **Visual style** — prepended to each scene’s image prompt in the storyboard (and merged with the usual conditioning and negatives).
- **Negatives** — extra comma-separated phrases merged into the default negative prompt for diffusion.
- **Use project default voice** — when checked, global **Voice model** from Settings/API is used. When unchecked, you can use **System TTS** (`pyttsx3`), optional **Kokoro speaker** (when that path is enabled), or **ElevenLabs** if enabled under the API tab with a valid key (see [elevenlabs.md](elevenlabs.md)).
- **ElevenLabs voice** — when the API tab has ElevenLabs enabled and a key present, the Characters tab lists cloud voices; stored as `elevenlabs_voice_id`. Used for narration only when default voice is off and ElevenLabs is configured.

## Run tab

Choose **Character** `(None)` to disable, or pick a saved character. The selection is stored as `active_character_id` in `ui_settings.json` and applied for the next pipeline run (including Preview / Storyboard workers).

## Pipeline

- **Script**: character context is appended to the brain prompt after the personality block.
- **Images**: visual style and character negatives are applied in `build_storyboard` (and for prebuilt preview prompts in `main.run_once` when applicable).
- **TTS**: when default voice is off, `synthesize()` may use ElevenLabs (if enabled + voice id), else Kokoro, else `pyttsx3`.
