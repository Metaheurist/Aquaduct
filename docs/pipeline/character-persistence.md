# Auto-cast persistence (Phase 8)

When the user picks **(None)** in the Characters dropdown on the Run tab, every run
generates an *ephemeral cast* via the script LLM
(`generate_cast_from_storyline_llm`) or the deterministic fallback
(`fallback_cast_for_show`). Phase 8 brings these auto-generated cast members up to
**feature parity with the Characters tab** and (by default) saves them to the global
character store so they can be re-used or edited next time.

## Schema parity with the Characters tab

`generate_cast_from_storyline_llm` now asks the LLM for an additional `voice_instruction`
field per character. `fallback_cast_for_show` mirrors the same shape for every video
format. Each generated cast member therefore carries:

| Field               | Used by                                                    |
|---------------------|-------------------------------------------------------------|
| `name`              | Brain prompt + UI label                                     |
| `role`              | Brain prompt context                                        |
| `identity`          | Brain prompt + Character profile                            |
| `visual_style`      | Image/video affixes + Character profile                     |
| `negatives`         | Image/video negative-prompt + Character profile             |
| `voice_instruction` | MOSS-VoiceGenerator / ElevenLabs / Character profile        |

This matches the dataclass `src.content.characters_store.Character` exactly (the only
optional fields the user can fill in by hand are TTS engine IDs and a portrait image).

## Promotion to the global store

`src/content/characters_store.py` adds two helpers:

```python
cast_to_characters(*, cast, video_format, headline_seed="") -> list[Character]
merge_cast_into_store(*, cast, video_format, headline_seed="") -> list[Character]
```

`cast_to_characters` builds full `Character` instances. The IDs are deterministic —
derived from `(name, video_format, headline_seed)` via Adler-32 + a UUID5 suffix — so:

- Re-running the same article does not duplicate cast entries; entries are upserted.
- Different video formats keep their own profiles (a “Lead” for `cartoon` is a
  different store entry than a “Lead” for `creepypasta`).

`merge_cast_into_store` loads `data/characters.json`, upserts the new `Character`s by
ID, and writes the file back. The function is **idempotent** and never deletes entries
that aren’t in the supplied cast.

## Pipeline integration

Both `main.run_once` (local LLM path) and `src.runtime.pipeline_api.run_once_api`
(API path) call `merge_cast_into_store(...)` immediately after writing the per-run
`assets/generated_cast.json` sidecar — but only when:

- the user has not selected an explicit character (so the cast is auto-generated), and
- `AppSettings.auto_save_generated_cast` is `True` (the default).

The local path also emits a `cast_persist` pipeline notice listing the saved names so
the user can see what arrived in the Characters tab without leaving the Run view.

## Settings & UI

A new boolean `AppSettings.auto_save_generated_cast` (default `True`) controls the
behaviour. The Run tab adds a checkbox **"Save generated cast to Characters tab"**
right under the Character dropdown (`UI/tabs/run_tab.py`). The choice is round-tripped
through `src/settings/ui_settings.py` and `UI/main_window.py` like every other
boolean setting.

## Tests

`tests/content/test_cast_persistence.py` covers:

- Field parity with the `Character` dataclass (every generated member fills identity,
  visual_style, negatives, and voice_instruction).
- Deterministic IDs across re-runs and per-format ID separation.
- `merge_cast_into_store` creates the file, is idempotent, preserves hand-authored
  entries, and short-circuits on empty input.
- `fallback_cast_for_show` includes `voice_instruction` for every supported format.
- `cast_to_ephemeral_character` aggregates voice directions for multi-character
  formats (cartoon/unhinged) and propagates the narrator instruction for single-host
  formats (news/explainer/creepypasta/health_advice).
