# Debug category: `storyboard`

**Where:** Storyboard flow — Manifest and scene grid

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["storyboard"] = True``
2. Or environment: ``AQUADUCT_DEBUG=storyboard`` or ``AQUADUCT_DEBUG_STORYBOARD=1``
3. Or CLI: ``python main.py --once --debug storyboard`` / ``python -m UI --debug storyboard``

## Logs

Lines look like ``[Aquaduct:storyboard] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
