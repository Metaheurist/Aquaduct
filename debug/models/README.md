# Debug category: `models`

**Where:** src/models/model_manager.py — HF downloads and snapshots

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["models"] = True``
2. Or environment: ``AQUADUCT_DEBUG=models`` or ``AQUADUCT_DEBUG_MODELS=1``
3. Or CLI: ``python main.py --once --debug models`` / ``python -m UI --debug models``

## Logs

Lines look like ``[Aquaduct:models] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
