# Debug category: `brain`

**Where:** src/content/brain.py — Local / API LLM script generation

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["brain"] = True``
2. Or environment: ``AQUADUCT_DEBUG=brain`` or ``AQUADUCT_DEBUG_BRAIN=1``
3. Or CLI: ``python main.py --once --debug brain`` / ``python -m UI --debug brain``

## Logs

Lines look like ``[Aquaduct:brain] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
