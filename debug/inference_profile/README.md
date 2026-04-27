# Debug category: `inference_profile`

**Where:** src/models/inference_profiles.py — VRAM bands and profile report

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["inference_profile"] = True``
2. Or environment: ``AQUADUCT_DEBUG=inference_profile`` or ``AQUADUCT_DEBUG_INFERENCE_PROFILE=1``
3. Or CLI: ``python main.py --once --debug inference_profile`` / ``python -m UI --debug inference_profile``

## Logs

Lines look like ``[Aquaduct:inference_profile] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
