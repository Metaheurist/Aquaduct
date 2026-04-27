# Debug category: `pipeline`

**Where:** main.run_once — Pipeline orchestration and stage flow

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["pipeline"] = True``
2. Or environment: ``AQUADUCT_DEBUG=pipeline`` or ``AQUADUCT_DEBUG_PIPELINE=1``
3. Or CLI: ``python main.py --once --debug pipeline`` / ``python -m UI --debug pipeline``

## Logs

Lines look like ``[Aquaduct:pipeline] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
