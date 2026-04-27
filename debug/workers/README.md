# Debug category: `workers`

**Where:** UI/workers/impl.py — Pipeline, preview, storyboard threads

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["workers"] = True``
2. Or environment: ``AQUADUCT_DEBUG=workers`` or ``AQUADUCT_DEBUG_WORKERS=1``
3. Or CLI: ``python main.py --once --debug workers`` / ``python -m UI --debug workers``

## Logs

Lines look like ``[Aquaduct:workers] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
