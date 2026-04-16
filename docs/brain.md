# `src/brain.py` — Brain (Script generator)

## Purpose
Convert scraped headlines/links into a short-form **tool review** package:
- a ~50s narration split into **few-second beats**
- **cyberpunk/high-contrast** visual prompts per beat
- upload-ready **title**, **description**, and **hashtags**

## Primary mode (local LLM)
Attempts to run:
- `meta-llama/Llama-3.2-3B-Instruct`
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

## Main entrypoint
- `generate_script(model_id: str, items: list[dict[str,str]], topic_tags: list[str] | None) -> VideoPackage`

## Character context
When the Run tab selects a **character** (see [Characters](characters.md)), an extra block is added so narration and on-screen text stay consistent with that host identity (layered on top of **Personality** presets).

## Topic tags
If `topic_tags` are provided (from the UI Topics tab list for the **current video format**, via `effective_topic_tags()`), they are injected into the prompt to bias:
- which tool release is selected
- the angle of the script
- the hashtag set

