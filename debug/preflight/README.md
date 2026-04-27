# Debug category: `preflight`

**Where:** src/runtime/preflight.py — Run preflight validation

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["preflight"] = True``
2. Or environment: ``AQUADUCT_DEBUG=preflight`` or ``AQUADUCT_DEBUG_PREFLIGHT=1``
3. Or CLI: ``python main.py --once --debug preflight`` / ``python -m UI --debug preflight``

## Logs

Lines look like ``[Aquaduct:preflight] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
