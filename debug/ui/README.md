# Debug category: `ui`

**Where:** UI/main_window.py — Shell actions, tabs, downloads

## UI modernization (2026)

Shared widgets and tab layout changes are documented in [docs/ui/shared-widgets.md](../../docs/ui/shared-widgets.md). When debugging Topics chips, Characters cards, or branding section visibility, start with `UI/tabs/topics_tab.py`, `characters_tab.py`, `branding_tab.py`, and `MainWindow._apply_media_mode_ui`.

## Enable

1. Edit [debug_log.py](../debug_log.py): set ``MODULE_DEBUG_FLAGS["ui"] = True``
2. Or environment: ``AQUADUCT_DEBUG=ui`` or ``AQUADUCT_DEBUG_UI=1``
3. Or CLI: ``python main.py --once --debug ui`` / ``python -m UI --debug ui``

## Logs

Lines look like ``[Aquaduct:ui] ...`` on stderr and under ``logs/debug.log`` when enabled.

← [Debug index](../README.md) · [debug_log.py](../debug_log.py)

---

*Desktop UI (2026 polish): [docs/ui/ui.md](docs/ui/ui.md) · [shared widgets](docs/ui/shared-widgets.md)*
