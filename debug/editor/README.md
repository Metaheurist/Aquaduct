# Debug category: `editor`

**Where:** src/render/editor.py — Micro-clips and final concat

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["editor"] = True``
2. Or environment: ``AQUADUCT_DEBUG=editor`` or ``AQUADUCT_DEBUG_EDITOR=1``
3. Or CLI: ``python main.py --once --debug editor`` / ``python -m UI --debug editor``

## Logs

Lines look like ``[Aquaduct:editor] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
