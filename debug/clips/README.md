# Debug category: `clips`

**Where:** src/render/clips.py — Text/image-to-video clips

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["clips"] = True``
2. Or environment: ``AQUADUCT_DEBUG=clips`` or ``AQUADUCT_DEBUG_CLIPS=1``
3. Or CLI: ``python main.py --once --debug clips`` / ``python -m UI --debug clips``

## Logs

Lines look like ``[Aquaduct:clips] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
