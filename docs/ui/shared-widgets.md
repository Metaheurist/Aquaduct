# Shared UI widgets (modernization)

Reusable building blocks added in the 2026 UI polish pass. Prefer these over ad-hoc layouts and unicode status glyphs.

## SVG toolbar icons

[`UI/widgets/toolbar_svg_icons.py`](../../UI/widgets/toolbar_svg_icons.py) — `qicon_toolbar(kind, color_hex, size)` and `pixmap_toolbar(...)` for compact toolbars.

Kinds include: `check`, `cross`, `dot`, `half`, `warning`, `info`, `chevron_right`, `chevron_down`, `arrow_left`, `arrow_right`, `sparkles`, plus existing `refresh`, `pause`, `play`, `stop`, folder/duplicate/trash.

## Status glyphs

[`UI/widgets/tab_sections.py`](../../UI/widgets/tab_sections.py):

- `status_glyph_label(kind, text, color_token=…)` — icon + label row for readiness / model badges
- `status_glyph_set_text(row, text, kind=…)` — update an existing row

Replaces unicode checkmarks and warning symbols in the Model and Run tabs.

## Flow layout

[`UI/widgets/flow_layout.py`](../../UI/widgets/flow_layout.py) — wrapping `QLayout` for Topics tag chips and the Characters card grid.

## Two-column rows

[`UI/widgets/two_column.py`](../../UI/widgets/two_column.py) — `two_column_row(left, right, ratio=(1,1), spacing=12)` for side-by-side section cards (Library media + runs, Characters grid + editor).

## Topic chips

[`UI/widgets/topic_chip.py`](../../UI/widgets/topic_chip.py) — removable pill chips with select + remove signals. Used on the Topics tab (~160px capped scroll area).

## Character cards

[`UI/widgets/character_card.py`](../../UI/widgets/character_card.py) — avatar, name, and identity snippet; click to select. Used in the Characters tab card grid.

## Button chrome

[`UI/theme/palette.py`](../../UI/theme/palette.py) — rounder `QPushButton` radii; `QPushButton[shape="pill"]` and `QPushButton[shape="circle"]` for icon-only controls.

Title-bar and dialog buttons: [`UI/widgets/title_bar_outline_button.py`](../../UI/widgets/title_bar_outline_button.py) (`styled_outline_button`, icon-only close/pause).

## Tests

- [`tests/ui/test_ui_modernization_widgets.py`](../../tests/ui/test_ui_modernization_widgets.py)
- [`tests/ui/test_ui_modernization_tabs.py`](../../tests/ui/test_ui_modernization_tabs.py)
- [`tests/ui/test_ui_preflight_install_prompt.py`](../../tests/ui/test_ui_preflight_install_prompt.py)

See [Desktop UI overview](ui.md).

---

*Desktop UI (2026 polish): [docs/ui/ui.md](docs/ui/ui.md) · [shared widgets](docs/ui/shared-widgets.md)*
