# Characters (Character Builder)

User-defined **characters** store a host identity, optional diffusion visual style and negatives, and optional narration voice overrides. They are saved in `data/characters.json` under the project root.

## Fields

- **Name** — list label and script context.
- **Identity / persona** — fed to the LLM as extra context so narration and on-screen text stay consistent with the chosen **Personality** preset on the Run tab (personality controls tone; character adds who-the-host-is). A **🧠** control in the field corner can **expand or improve** the text using the project **Script (LLM)** (see [`UI/brain_expand.py`](../../UI/brain_expand.py), [`expand_custom_field_text` in `src/content/brain.py`](../../src/content/brain.py), [Brain](../pipeline/brain.md)).
- **Visual style** — prepended to each scene’s image prompt in the storyboard (and merged with the usual conditioning and negatives). Same optional **🧠** expansion.
- **Negatives** — extra comma-separated phrases merged into the default negative prompt for diffusion. Same optional **🧠** expansion.

The tab uses a **compact** layout (short character list, horizontal add/duplicate/delete, capped text heights) so more fits on screen at once.

### Auto presets (LLM)

At the top, **Preset** lists built-in archetypes (e.g. **Unhinged comedy**, **Gen Z / chronically online**, deadpan anchor, cozy host, tech-bro satire, anime mascot energy, noir narrator, …). Definitions live in [`src/content/character_presets.py`](../../src/content/character_presets.py). **Generate with LLM** uses the **Script (LLM)** model selected on the **Model** tab (same resolution as 🧠 expand — see [`resolve_llm_model_id`](../../UI/brain_expand.py) in [Models](../reference/models.md)). It calls [`generate_character_from_preset_llm` in `src/content/brain.py`](../../src/content/brain.py) and expects a JSON object with `name`, `identity`, `visual_style`, `negatives`, and `use_default_voice`. **Gated** Hub models require **API → Hugging Face** token + license acceptance on the model page. The form is filled in place; click **Save character** to persist. Optional **extra notes** steer the generation without replacing the preset. Pyttsx3 / Kokoro / ElevenLabs voice IDs are **not** auto-picked — choose those after the text profile is generated.

- **Use project default voice** — when checked, global **Voice model** from Settings/API is used. When unchecked, you can use **System TTS** (`pyttsx3`), optional **Kokoro speaker** (when that path is enabled), or **ElevenLabs** if enabled under the API tab with a valid key (see [elevenlabs.md](../integrations/elevenlabs.md)).
- **ElevenLabs voice** — when the API tab has ElevenLabs enabled and a key present, the Characters tab lists cloud voices; stored as `elevenlabs_voice_id`. Used for narration only when default voice is off and ElevenLabs is configured.

## Run tab

Choose **Character** `(None)` to disable, or pick a saved character. The selection is stored as `active_character_id` in `ui_settings.json` and applied for the next pipeline run (including Preview / Storyboard workers).

## Portrait preview

Beside **Generate portrait**, the small thumbnail shows the resolved reference image when a file exists. **Click** the thumbnail to open a **maximized** borderless preview (`FramelessDialog`, title **`Portrait — <character name>`**); the image scales with the window **keeping aspect ratio**. The **No portrait** placeholder is not clickable until you generate or assign an image path.

## Pipeline

- **Script**: character context is appended to the brain prompt after the personality block.
- **Images**: visual style and character negatives are applied in `build_storyboard` (and for prebuilt preview prompts in `main.run_once` when applicable).
- **TTS**: when default voice is off, `synthesize()` may use ElevenLabs (if enabled + voice id), else Kokoro, else `pyttsx3`.
