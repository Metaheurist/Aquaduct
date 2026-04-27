# Debug category: `artist`

**Where:** src/render/artist.py — Diffusion image generation

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["artist"] = True``
2. Or environment: ``AQUADUCT_DEBUG=artist`` or ``AQUADUCT_DEBUG_ARTIST=1``
3. Or CLI: ``python main.py --once --debug artist`` / ``python -m UI --debug artist``

## Logs

Lines look like ``[Aquaduct:artist] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
