# Debug category: `branding`

**Where:** Branding / palette — Prompt styling

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["branding"] = True``
2. Or environment: ``AQUADUCT_DEBUG=branding`` or ``AQUADUCT_DEBUG_BRANDING=1``
3. Or CLI: ``python main.py --once --debug branding`` / ``python -m UI --debug branding``

## Logs

Lines look like ``[Aquaduct:branding] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
