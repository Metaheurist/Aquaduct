# Aquaduct debug logging

Central module: **[debug_log.py](debug_log.py)** — categorical `dprint()`, env / CLI merging, and **`MODULE_DEBUG_FLAGS`** (boolean per category; edit in-repo to enable without env).

## Enabling categories

| Mechanism | Example |
|-----------|---------|
| **Booleans** | In `debug_log.py`, set `MODULE_DEBUG_FLAGS["pipeline"] = True` |
| **Env** | `AQUADUCT_DEBUG=pipeline,brain` or `AQUADUCT_DEBUG=all` |
| **Per-var env** | `AQUADUCT_DEBUG_PIPELINE=1` |
| **CLI** | `python main.py --once --debug brain` · `python -m UI --debug ui,workers` |
| **Always-on stages** | Coarse `[Aquaduct][run] [stage_name] …` lines (no env) from [`pipeline_console()`](debug_log.py) — see stderr and `logs/debug.log` |

Resolution is a **union**: booleans OR env OR CLI combined (then cached until `invalidate_debug_cache()`).

## Tools

```text
python -m debug.tools.print_active
python -m debug.tools.smoke_categories
python -m debug.print_active          # shim → tools.print_active
```

Requires repo root on `PYTHONPATH` (running from repo root as above is fine).

## Categories (index)

| Area | Category | README |
|------|-----------|--------|
| Orchestration | `pipeline` | [pipeline/README.md](pipeline/README.md) |
| News / crawl | `crawler` | [crawler/README.md](crawler/README.md) |
| LLM scripts | `brain` | [brain/README.md](brain/README.md) |
| TTS | `voice` | [voice/README.md](voice/README.md) |
| Images | `artist` | [artist/README.md](artist/README.md) |
| FFmpeg assembly | `editor` | [editor/README.md](editor/README.md) |
| Motion clips | `clips` | [clips/README.md](clips/README.md) |
| Storyboard UI | `storyboard` | [storyboard/README.md](storyboard/README.md) |
| Story stages | `story_pipeline` | [story_pipeline/README.md](story_pipeline/README.md) |
| Audio mix | `audio` | [audio/README.md](audio/README.md) |
| HF / snapshots | `models` | [models/README.md](models/README.md) |
| Preflight | `preflight` | [preflight/README.md](preflight/README.md) |
| Branding | `branding` | [branding/README.md](branding/README.md) |
| Topics / discover | `topics` | [topics/README.md](topics/README.md) |
| UI threads | `workers` | [workers/README.md](workers/README.md) |
| Main window | `ui` | [ui/README.md](ui/README.md) |
| Tasks tab | `tasks` | [tasks/README.md](tasks/README.md) |
| Settings | `config` | [config/README.md](config/README.md) |
| OpenAI-compat HTTP | `openai` | [openai/README.md](openai/README.md) |
| Inference / VRAM report | `inference_profile` | [inference_profile/README.md](inference_profile/README.md) |
| Stage cleanup / RAM–VRAM | `memory_budget` | [memory_budget/README.md](memory_budget/README.md) |
| Multi-GPU placement | `gpu_plan` | [gpu_plan/README.md](gpu_plan/README.md) |
| Web context | `story_context` | [story_context/README.md](story_context/README.md) |

Aliases (see `debug_log.py`): `run→pipeline`, `llm→brain`, `hf→models`, `api→openai`, etc.

## Adding a category

1. Append to `DEBUG_CATEGORIES` and `MODULE_DEBUG_FLAGS` in [debug_log.py](debug_log.py).
2. Add `debug/<category>/README.md`.
3. Run tests / update category registry check if present.
