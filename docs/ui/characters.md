# Characters (Character Builder)

User-defined **characters** store a host identity, optional diffusion visual style and negatives, and optional narration voice overrides. They are saved in `data/characters.json` under the project root.

## Layout

- **Left**: scrollable **card grid** — round avatar, name, and one-line identity snippet ([`CharacterCard`](../../UI/widgets/character_card.py), [`FlowLayout`](../../UI/widgets/flow_layout.py)).
- **Right**: profile editor (form fields, portrait, voice options).
- Toolbar (**add** / **duplicate** / **delete**) uses SVG icons ([`UI/widgets/toolbar_svg_icons.py`](../../UI/widgets/toolbar_svg_icons.py)).

## Fields

- **Name** — card label and script context.
- **Identity / persona** — LLM context for narration consistency. Optional **sparkles** (LLM expand) in the field corner ([`UI/services/brain_expand.py`](../../UI/services/brain_expand.py), [Brain](../pipeline/brain.md)).
- **Visual style** / **Negatives** — storyboard and diffusion hints; optional LLM expand on each.
- **Gender**, **Ethnicity**, **Age band** — optional anchoring strings for script and storyboard.

## Auto presets (LLM)

**Preset** lists built-in archetypes ([`src/content/character_presets.py`](../../src/content/character_presets.py)). **Generate with LLM** uses the **Script (LLM)** model from the **Model** tab ([`resolve_llm_model_id`](../../UI/services/brain_expand.py)). Click **Save character** to persist.

## Run tab

Pick **one or more** saved characters (ordered list — **first = Lead**). Stored as `active_character_ids` in `ui_settings.json`.

## Portrait preview

**Generate portrait** updates the card avatar. Click the thumbnail for a maximized preview dialog.

## Pipeline

- **Script**: character context appended after personality block.
- **Images**: identity tokens + visual style in storyboard prompts.
- **TTS**: ElevenLabs / Kokoro / pyttsx3 when default voice is off.

See [shared widgets](shared-widgets.md) and [Desktop UI](ui.md).
