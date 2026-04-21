# `src/content/brain.py` — Brain (Script generator)

## Purpose
Convert scraped headlines/links into a short-form **tool review** package:
- a ~50s narration split into **few-second beats**
- **cyberpunk/high-contrast** visual prompts per beat
- upload-ready **title**, **description**, and **hashtags**

## Primary mode (local LLM)
Attempts to run:
- `Qwen/Qwen3-14B-Instruct` (default curated **Qwen3 14B** instruct; Fimbulvetr 11B, Midnight Miqu 70B, and **DeepSeek-V3** 671B MoE are also listed for heavier / reasoning workloads — see [models](../reference/models.md))
- in **4-bit** using `bitsandbytes`

## Fallback mode
If the local model fails to load (common on some Windows setups), it returns a deterministic template package so the pipeline can still produce a video end-to-end.

## Output structure
`VideoPackage` includes:
- `title`
- `description`
- `hashtags` (15–30 recommended; normalized to `#Tag`)
- `hook`
- `segments[]`: `{ narration, visual_prompt, on_screen_text? }`
- `cta`

## Inference profiles (local)
When the desktop app or `run_once` passes **`inference_settings`** (`AppSettings`), [`_generate_with_transformers`](../../src/content/brain.py) tightens **`max_new_tokens`** and the tokenizer **input** cap using [`pick_script_profile`](../../src/models/inference_profiles.py) and the same **effective script VRAM** as the GPU policy fit badges. **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** still overrides the input cap when set. See [Inference profiles](../reference/inference_profiles.md).

## Main entrypoint
- `generate_script(..., items: list[dict[str,str]], topic_tags: list[str] | None, creative_brief: str | None = None, video_format: str = "news", inference_settings: AppSettings | None = None, ...) -> VideoPackage`
  - **Preset runs**: `items` are scraped headlines; prompt is built from `items` + tags + personality.
  - **Custom runs** (desktop **Run → Custom**): set `creative_brief` to the output of **`expand_custom_video_instructions`** (first LLM pass; plain-text structured brief). `items` may be a single synthetic row (`source: "custom"`) for metadata. `video_format` steers tone hints in the prompt.

## Custom run mode (LLM expansion + package)
- **`expand_custom_video_instructions`**: first pass — turns rough user notes into a labeled creative brief (plain text, not JSON).
- **`generate_script`** with `creative_brief` set: second pass — same JSON schema as headline mode, but the primary directive is the expanded brief (`_prompt_for_creative_brief`). On failure, **`_fallback_package_custom`** builds a minimal package from the brief text instead of the generic “tool news” fallback.

## Character context
When the Run tab selects a **character** (see [Characters](../ui/characters.md)), an extra block is added so narration and on-screen text stay consistent with that host identity (layered on top of **Personality** presets).

## Topic tags
If `topic_tags` are provided (from the UI Topics tab list for the **current video format**, via `effective_topic_tags()`), they are injected into the prompt to bias:
- which tool release is selected
- the angle of the script
- the hashtag set

## UI field expansion (`expand_custom_field_text`)
For free-form text in the desktop app (character fields, topic tag line, storyboard scene prompt), the **🧠** button calls **`expand_custom_field_text`** with the user’s draft (or empty) and a short field label. It reuses the same local transformer path as script generation (`_generate_with_transformers`), then strips common markdown wrappers from the reply. Implemented in [`src/content/brain.py`](../../src/content/brain.py); runs off the GUI thread via **`TextExpandWorker`** in [`UI/workers.py`](../../UI/workers.py), which applies the saved Hugging Face token via [`ensure_hf_token_in_env`](../../src/models/hf_access.py) when needed and maps gated-repo / 401 errors with [`humanize_hf_hub_error`](../../src/models/hf_access.py).

## Character generation from presets (`generate_character_from_preset_llm`)
The **Characters** tab can fill all text fields from a built-in archetype: **`generate_character_from_preset_llm`** in [`src/content/brain.py`](../../src/content/brain.py) asks the script LLM for a single JSON object (`name`, `identity`, `visual_style`, `negatives`, `use_default_voice`). Preset definitions live in [`src/content/character_presets.py`](../../src/content/character_presets.py). The **Script (LLM)** repo id comes from **`resolve_llm_model_id`** in [`UI/brain_expand.py`](../../UI/brain_expand.py) (Model tab combo first, then saved settings).

## Which repo id is used for “brain” UI tasks?
**`resolve_llm_model_id(win)`** returns, in order: **`llm_combo.currentData()`** if set, else **`settings.llm_model_id`**, else the default from **`get_models()`**. This keeps 🧠 expand and character generation aligned with the **Model** tab selection even before the user clicks **Save settings**.

