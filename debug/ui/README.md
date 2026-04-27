# Debug category: `ui`

**Where:** UI/main_window.py — Shell actions, tabs, downloads

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["ui"] = True``
2. Or environment: ``AQUADUCT_DEBUG=ui`` or ``AQUADUCT_DEBUG_UI=1``
3. Or CLI: ``python main.py --once --debug ui`` / ``python -m UI --debug ui``

## Logs

Lines look like ``[Aquaduct:ui] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
