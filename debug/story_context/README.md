# Debug category: `story_context`

**Where:** src/content/story_context.py — Firecrawl / web digest

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["story_context"] = True``
2. Or environment: ``AQUADUCT_DEBUG=story_context`` or ``AQUADUCT_DEBUG_STORY_CONTEXT=1``
3. Or CLI: ``python main.py --once --debug story_context`` / ``python -m UI --debug story_context``

## Logs

Lines look like ``[Aquaduct:story_context] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
