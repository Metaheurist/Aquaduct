# `src/content/brain.py` — Brain (Script generator)

## Purpose
Convert scraped headlines/links into a short-form **tool review** package:
- a ~50s narration split into **few-second beats**
- **cyberpunk/high-contrast** visual prompts per beat
- upload-ready **title**, **description**, and **hashtags**

## Primary mode (local LLM)
Attempts to run:
- `Qwen/Qwen3-14B` (default curated **Qwen3 14B** chat/instruct repo; Fimbulvetr 11B, Midnight Miqu 70B, and **DeepSeek-V3** 671B MoE are also listed for heavier / reasoning workloads — see [models](../reference/models.md))
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

### Validator: `_to_package` synthesizes missing fields (Phase 3)

Real LLM output frequently emits beats with only `narration` (or only
`visual_prompt`). The pre-Phase-3 validator dropped those segments silently,
which on the `Two_Sentenced_Horror_Stories` run collapsed the storyboard to a
single placeholder beat — the visible "stitched motion pictures" effect was
amplified by this loss.

`_to_package(data, *, video_format="")` now:

1. Drops only segments where **both** fields are empty.
2. Synthesizes a `visual_prompt` from `narration` (and `on_screen_text` /
   title) using a small format-aware affix (`creepypasta` → atmospheric
   horror still; `cartoon` → bold linework; `health_advice` → clean
   infographic; etc.).
3. Synthesizes a `narration` from `visual_prompt` when only the visual is
   present (kept short and speakable).
4. Falls back to a single placeholder segment only when *every* segment is
   empty.

`video_package_from_llm_output(text, *, video_format="")` threads the active
format through the validator. Both transformers (`generate_script`) and
OpenAI (`generate_script_openai`) callers pass the active format. Refinement
stages in [`src/content/story_pipeline.py`](../../src/content/story_pipeline.py)
also propagate the format on each repair / retry.

The `creepypasta` prompt now states explicitly that empty `visual_prompt`
makes a segment unusable; this is paired with the validator above so partial
outputs degrade gracefully instead of becoming the new failure mode.

## Inference profiles (local)
When the desktop app or `run_once` passes **`inference_settings`** (`AppSettings`), [`_infer_text_with_optional_holder`](../../src/content/brain.py) tightens **`max_new_tokens`** and the tokenizer **input** cap (via **`_generate_with_loaded_causal_lm`**) using [`pick_script_profile`](../../src/models/inference_profiles.py) and the same **effective script VRAM** as the GPU policy fit badges. **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** still overrides the input cap when set. See [Inference profiles](../reference/inference_profiles.md).

## Shared LLM holder (fewer reloads)
The desktop pipeline passes a mutable **`llm_holder`** dict across successive brain calls (**`expand_custom_video_instructions`**, **`generate_script`**, story refinement, cast, …) so **`_infer_text_with_optional_holder`** swaps or reuses **`AutoModelForCausalLM`** in place ([`src/content/llm_session.py`](../../src/content/llm_session.py)). When **`llm_holder`** is **`None`** (CLI / one-shot), each call loads, infers, and disposes the pair (legacy behaviour). See [Crash resilience — LLM holder](crash-resilience.md).

## Quantization
[`load_causal_lm_from_pretrained`](../../src/content/brain.py) accepts an explicit **`quant_mode`** (`auto | bf16 | fp16 | int8 | nf4_4bit`) sourced from `AppSettings.script_quant_mode`. The loader resolves `auto` against the **effective script VRAM**, attempts the corresponding `BitsAndBytesConfig` (4-bit NF4 / 8-bit) or fp16 / bf16 dtype, and falls back to fp16 / CPU on failure with a status message. The legacy `try_llm_4bit=True` continues to work and is migrated to `script_quant_mode="nf4_4bit"` on first save. See [Quantization](../reference/quantization.md).

## Main entrypoint
- `generate_script(..., items: list[dict[str,str]], topic_tags: list[str] | None, creative_brief: str | None = None, video_format: str = "news", inference_settings: AppSettings | None = None, ...) -> VideoPackage`
  - **Preset runs**: `items` are scraped headlines; prompt is built from `items` + tags + personality.
  - **Custom runs** (desktop **Run → Custom**): set `creative_brief` to the output of **`expand_custom_video_instructions`** (first LLM pass; plain-text structured brief). `items` may be a single synthetic row (`source: "custom"`) for metadata. `video_format` steers tone hints in the prompt.

## Custom run mode (LLM expansion + package)
- **`expand_custom_video_instructions`**: first pass — turns rough user notes into a labeled creative brief (plain text, not JSON).
- **`generate_script`** with `creative_brief` set: second pass — same JSON schema as headline mode, but the primary directive is the expanded brief (`_prompt_for_creative_brief`). On failure, **`_fallback_package_custom`** builds a minimal package from the brief text instead of the generic “tool news” fallback.

## Character context
When the Run tab selects a **character** (see [Characters](../ui/characters.md)), an extra block is added so narration and on-screen text stay consistent with that host identity (layered on top of **Personality** presets).

## Topic tags & hard constraints

If `topic_tags` are provided (from the Topics tab list for the **current video format**, via [`effective_topic_tags()`](../../src/content/topics.py)), they drive crawling and scripting. **Phase 6** upgrades them from a soft bias to **hard anchors**:

- **`main.py`** appends [`topic_constraints_block()`](../../src/content/topic_constraints.py) to `script_digest` after [`StyleContext`](../../src/content/prompt_context.py) merges — the block lists every tag as a **must** for angle, hashtags, hooks, and segment beats.
- Optional **`topic_tag_notes`** (per-tag grounding lines edited on the Topics tab; persisted in `ui_settings.json`) attach as **`Tag context: &lt;tag&gt; → &lt;note&gt;`** in that same block ([Topics UI](../ui/topics.md)).
- Cast names from the active **Character(s)** feed the block so narration stays anchored to declared speakers ([character persistence](character-persistence.md)).
- URL **source quality** (`score_source_url` / `assets/source_quality.json`) is heuristic only; pairing with chunked article relevance is documented in [`article-relevance.md`](article-relevance.md).

Format-specific prompts (`_prompt_for_*`) still spell out tag lines (`Topic tags (HARD constraint — …)` for creepypasta, news, explainer, wellness) so the structured JSON stays on-brief after the fused digest arrives.

## UI field expansion (`expand_custom_field_text`)
For free-form text in the desktop app (character fields, topic tag line, storyboard scene prompt), the **🧠** button calls **`expand_custom_field_text`** with the user’s draft (or empty) and a short field label. It reuses the same local transformer path as script generation (`_generate_with_transformers`), then strips common markdown wrappers from the reply. Implemented in [`src/content/brain.py`](../../src/content/brain.py); runs off the GUI thread via **`TextExpandWorker`** in [`UI/workers.py`](../../UI/workers.py), which applies the saved Hugging Face token via [`ensure_hf_token_in_env`](../../src/models/hf_access.py) when needed and maps gated-repo / 401 errors with [`humanize_hf_hub_error`](../../src/models/hf_access.py).

## Character generation from presets (`generate_character_from_preset_llm`)
The **Characters** tab can fill all text fields from a built-in archetype: **`generate_character_from_preset_llm`** in [`src/content/brain.py`](../../src/content/brain.py) asks the script LLM for a single JSON object (`name`, `identity`, `visual_style`, `negatives`, `use_default_voice`). Preset definitions live in [`src/content/character_presets.py`](../../src/content/character_presets.py). The **Script (LLM)** repo id comes from **`resolve_llm_model_id`** in [`UI/brain_expand.py`](../../UI/brain_expand.py) (Model tab combo first, then saved settings).

## Which repo id is used for “brain” UI tasks?
**`resolve_llm_model_id(win)`** returns, in order: **`llm_combo.currentData()`** if set, else **`settings.llm_model_id`**, else the default from **`get_models()`**. This keeps 🧠 expand and character generation aligned with the **Model** tab selection even before the user clicks **Save settings**.

