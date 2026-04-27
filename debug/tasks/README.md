# Debug category: `tasks`

**Where:** Tasks tab — Queue rows, remove queued, refresh

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["tasks"] = True``
2. Or environment: ``AQUADUCT_DEBUG=tasks`` or ``AQUADUCT_DEBUG_TASKS=1``
3. Or CLI: ``python main.py --once --debug tasks`` / ``python -m UI --debug tasks``

## Logs

Lines look like ``[Aquaduct:tasks] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
