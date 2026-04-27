# Debug category: `voice`

**Where:** src/speech — TTS synthesis and timing JSON

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["voice"] = True``
2. Or environment: ``AQUADUCT_DEBUG=voice`` or ``AQUADUCT_DEBUG_VOICE=1``
3. Or CLI: ``python main.py --once --debug voice`` / ``python -m UI --debug voice``

## Logs

Lines look like ``[Aquaduct:voice] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
