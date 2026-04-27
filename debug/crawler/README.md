# Debug category: `crawler`

**Where:** Headline / news pipeline — Item selection and crawl seeds

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["crawler"] = True``
2. Or environment: ``AQUADUCT_DEBUG=crawler`` or ``AQUADUCT_DEBUG_CRAWLER=1``
3. Or CLI: ``python main.py --once --debug crawler`` / ``python -m UI --debug crawler``

## Logs

Lines look like ``[Aquaduct:crawler] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)
