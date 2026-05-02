# Scene-prompt builder (Phase 4)

[`src/render/scene_prompts.py`](../../src/render/scene_prompts.py) is the
single source of truth for the per-scene T2V/I2V prompts the Pro pipeline
sends to the video model. It replaces the inline logic that used to live
in `main._split_into_pro_scenes_from_script`, fixing three problems
visible in the `Two_Sentenced_Horror_Stories` run:

| Symptom | Root cause | Fix |
|---|---|---|
| Every clip rendered the article headline as on-screen text | Forced `"<title> | "` prefix on every prompt | Headline is dropped from T2V prompts entirely; lives in branding overlays only |
| Clips drifted toward stock animation regardless of cast | Cartoon/unhinged path used only segment text | Cast names parsed out of `character_context` and injected into each scene |
| 2-segment scripts produced 2 identical clips | Builder returned exactly `len(segments)` scenes | Optional LLM expansion tops up to `n_scenes` |

## Public API

```python
from src.render.scene_prompts import (
    SceneSpec,
    build_scene_prompts,
    expand_scenes_via_llm,
    specs_to_prompts,
)

specs = build_scene_prompts(
    pkg=pkg,                       # VideoPackage-shaped object
    fallback_prompts=storyboard_prompts,
    video_format="creepypasta",
    n_scenes=6,
    character_context=char_ctx,    # brain.character_context_for_brain(...)
    art_style_affix=style_ctx.as_t2v_affix(),
)
prompts = specs_to_prompts(specs)
```

`SceneSpec` carries `prompt`, `role` (`"hook" | "segment" | "cta" |
"expanded"`), and `source_index` so downstream stages can attribute a
generated clip back to a specific script beat.

`expand_scenes_via_llm(specs, target_count=6, video_format=..., invoke_llm=...)`
asks the script LLM to invent additional bridging beats when the script
yields fewer scenes than the Pro length preset wants. The caller passes a
single-shot callable so unit tests can stub the LLM without importing the
heavy brain stack.

## Format-specific behaviour

The module reads `video_format` to pick:

- **Motion cues** — per-format vocabulary used to keep consecutive clips
  visually distinct (`creepypasta` → "slow dolly into darkness", "rack
  focus through fog"; `cartoon` → "snap zoom, squash-stretch", "lunge to
  camera"; `news` → "slow push-in", "parallax drift"; etc.).
- **Style tail** — short composition note appended once per scene
  (`"9:16 vertical, low-key cinematic horror, fog and grain, no gore"`
  for `creepypasta`, etc.). Skipped if the caller already passes a richer
  `art_style_affix` for the same job.
- **Source preference** — comedy/horror formats favour
  `segment.visual_prompt`; news/explainer favour `segment.narration` so
  the spoken language drives the picture.

## Cast injection

`_extract_character_names` parses the `character_context` block produced
by `src/content/characters_store.py::character_context_for_brain` (Phase
8). Three patterns are recognised:

1. Bullet lines `- Name (Role): identity` (multi-character cast).
2. `Cast: Name & Foil` heading line.
3. `Character name: <name>` solo block (single-narrator formats).

Up to four names are kept; the first scene gets `"Lead and Foil, ..."`,
the next gets `"Foil and Lead, ..."`, etc., so the cast appears
consistently across the clip set without becoming a parade.

## Diversity guardrails

- `_ensure_unique_starts` rotates the first words of any scene whose
  4-word head matches the previous scene, so the prompt set never reads
  as a rerun of the same shot.
- `cap_words(prompt, n_words=40)` keeps every prompt within the ~77-token
  CLIP-class budget that mainstream T2V text encoders rely on.
- `SCENE_COUNT_MAX = 16` is a hard ceiling regardless of caller request,
  so a misconfigured preset can't ask CogVideoX-5b for 64 clips.

## Pipeline integration

`main.py::_split_into_pro_scenes_from_script` is now a thin wrapper that
forwards to `build_scene_prompts`. The Pro T2V/I2V branch in `run_once`
also computes a `StyleContext` (Phase 9) so the same `art_style_affix`
the script LLM saw flows into the scene prompts:

```python
style_ctx = compose_prompt_context(app=app, character_context=char_ctx)
pro_scenes = _split_into_pro_scenes_from_script(
    pkg=pkg,
    prompts=prompts,
    video_format=app.video_format,
    n_scenes=video_settings.clips_per_video or None,
    character_context=char_ctx,
    art_style_affix=style_ctx.as_t2v_affix(),
)
```

## Tests

[`tests/render/test_scene_prompts.py`](../../tests/render/test_scene_prompts.py)
covers 18 scenarios:

- Title prefix is removed for every format.
- Cartoon/unhinged formats use `visual_prompt` over `narration`.
- Cast names from a duo block appear in scenes; solo-narrator name appears
  for `creepypasta`.
- Genre cues are format-specific; style tails always include `9:16`.
- `n_scenes` truncates and `_ensure_unique_starts` breaks consecutive
  duplicates.
- `expand_scenes_via_llm` strips bullet/numbering noise, no-ops when
  `len(specs) >= target`, and swallows LLM errors so a flaky model
  doesn't crash the render.
- `specs_to_prompts` drops empty entries.

The legacy
[`tests/render/test_pro_scene_prompts.py`](../../tests/render/test_pro_scene_prompts.py)
was updated to assert *no* headline prefix appears in the news-format
output (the Phase 4 contract).
