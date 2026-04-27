# Debug category: `openai`

**Where:** src/platform/openai_client.py — OpenAI-compatible HTTP

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["openai"] = True``
2. Or environment: ``AQUADUCT_DEBUG=openai`` or ``AQUADUCT_DEBUG_OPENAI=1``
3. Or CLI: ``python main.py --once --debug openai`` / ``python -m UI --debug openai``

## Logs

Lines look like ``[Aquaduct:openai] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
