# Debug category: `story_pipeline`

**Where:** src/content/story_pipeline.py — Multi-stage story review

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["story_pipeline"] = True``
2. Or environment: ``AQUADUCT_DEBUG=story_pipeline`` or ``AQUADUCT_DEBUG_STORY_PIPELINE=1``
3. Or CLI: ``python main.py --once --debug story_pipeline`` / ``python -m UI --debug story_pipeline``

## Logs

Lines look like ``[Aquaduct:story_pipeline] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
