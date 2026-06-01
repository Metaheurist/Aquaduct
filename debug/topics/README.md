# Debug category: `topics`

**Where:** Topics / Discover — TopicDiscoverWorker

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["topics"] = True``
2. Or environment: ``AQUADUCT_DEBUG=topics`` or ``AQUADUCT_DEBUG_TOPICS=1``
3. Or CLI: ``python main.py --once --debug topics`` / ``python -m UI --debug topics``

## Logs

Lines look like ``[Aquaduct:topics] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)

---

*Desktop UI (2026 polish): [docs/ui/ui.md](docs/ui/ui.md) · [shared widgets](docs/ui/shared-widgets.md)*
