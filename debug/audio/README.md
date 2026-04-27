# Debug category: `audio`

**Where:** Audio polish — Music ducking and mix

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["audio"] = True``
2. Or environment: ``AQUADUCT_DEBUG=audio`` or ``AQUADUCT_DEBUG_AUDIO=1``
3. Or CLI: ``python main.py --once --debug audio`` / ``python -m UI --debug audio``

## Logs

Lines look like ``[Aquaduct:audio] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
