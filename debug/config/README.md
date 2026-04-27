# Debug category: `config`

**Where:** Settings — Load/save ui_settings

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["config"] = True``
2. Or environment: ``AQUADUCT_DEBUG=config`` or ``AQUADUCT_DEBUG_CONFIG=1``
3. Or CLI: ``python main.py --once --debug config`` / ``python -m UI --debug config``

## Logs

Lines look like ``[Aquaduct:config] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
