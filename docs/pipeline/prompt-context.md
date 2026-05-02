# Style fusion: prompt context (Phase 9)

`src/content/prompt_context.py` resolves the four style signals once per run
and exposes ready-to-paste prompt blocks for every downstream stage:

| Signal | Source | Used by |
|--------|--------|---------|
| `video_format` | `AppSettings.video_format` | LLM voice lock, T2V affix |
| `personality` | `AppSettings.personality_id` (auto-resolved) | Script LLM rules / guardrails |
| `art_style_id` | `AppSettings.art_style_preset_id` | Script LLM affix, T2I/T2V affix |
| `branding` | `AppSettings.branding` (palette + strength) | Script LLM affix, T2I/T2V affix |
| `character_context` | resolved character (or auto-cast, Phase 8) | Script LLM narration block |

## API

```python
from src.content.prompt_context import (
    compose_prompt_context,
    StyleContext,
    format_voice_lock,
    reconcile_format_personality,
    art_style_text_affix,
    branding_to_prompt_block,
    merge_with_supplement,
)

ctx = compose_prompt_context(app=settings, character_context=char_block)
script_supplement = merge_with_supplement(prior_supplement, ctx)
t2i_affix = ctx.as_t2i_affix()
t2v_affix = ctx.as_t2v_affix()
```

`StyleContext.as_script_prompt_block()` produces a Markdown block of the form:

```markdown
## Style fusion (applies to ALL segments)
- Video format: creepypasta
- Default voice: first-person past-tense campfire narrator …
- Personality: Neutral / Newsroom — Straight, factual, low-flair delivery. | rules: … | guardrails: …
- Art style: cohesive cinematic lighting, consistent color grade across shots, same film look
- Art style negatives: inconsistent lighting, jarring color shift between frames
- Branding (strength=subtle): deep blues, muted teal, gold accents
- Character (host) is provided in a separate block; honor it for narration only.
- Conflict notices:
  - Hype / Creator energy clashes with creepypasta dread; switching to neutral / cozy reading.
```

Aquaduct calls this block from `main.py`'s non-API script path so the
script LLM receives a single, deterministic style brief alongside the
existing web digest. The block is idempotent — re-merging the same context
into a supplement that already contains it does not duplicate.

## Format / personality reconciliation

`reconcile_format_personality(video_format, personality)` swaps clashing
combinations to a sane default and surfaces a human-readable warning that
flows into [`pipeline_notice`](../../src/runtime/pipeline_notice.py) and the
prompt itself. Current rules:

| Format | Bad personality | Replacement | Reason |
|--------|-----------------|-------------|--------|
| `creepypasta` | `hype` | `neutral` | Hype delivery undercuts dread. |
| `creepypasta` | `comedic` | `neutral` | Punchlines undercut horror tone. |
| `unhinged` | `neutral` | `comedic` | Newsroom delivery reads flat. |
| `unhinged` | `cozy` | `comedic` | Cozy is too gentle for sketches. |
| `health_advice` | `unhinged_chaos` | `cozy` | Chaotic delivery contradicts safety guidance. |
| `news` | `comedic` | `neutral` | May undercut news clarity. |

Add new rows in `_CONFLICTS` + `_CONFLICT_REPLACEMENTS` as creative
formats grow.

## How it ties into other phases

* **Phase 3** validator (`brain._to_package`) gets format-aware visual
  prompts; the StyleContext above guarantees the prompt itself is also
  format-aware so the LLM rarely has to fall back to the validator
  synthesis.
* **Phase 4** scene-prompt builder (`src/render/scene_prompts.py`) uses
  `StyleContext.as_t2v_affix()` to keep generated clip prompts on-style.
* **Phase 6** topic grounding adds source-quality and topic-tag notes
  into the same fusion block.
* **Phase 8** auto-cast persistence pre-fills `character_context` so the
  script LLM gets a real persona, not "auto / none".

## Tests

[`tests/content/test_prompt_context.py`](../../tests/content/test_prompt_context.py)
covers: known voice locks, conflict reconciliation per format/personality
pair, art-style affix lookup, branding block disabled/enabled, T2V affix
format hints, and merge idempotency.
