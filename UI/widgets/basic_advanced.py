"""Per-tab Basic | Advanced mode header and section visibility helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from UI.widgets.segmented_picker import SegmentOption, SegmentedPicker


def is_tab_advanced(settings, tab_id: str) -> bool:
    """Return True when the tab is in Advanced mode (default Basic)."""
    raw = getattr(settings, "advanced_tabs", None) or {}
    if not isinstance(raw, dict):
        return False
    return bool(raw.get(str(tab_id), False))


def set_tab_advanced(win, tab_id: str, advanced: bool, *, persist: bool = True) -> None:
    """Update in-memory settings and optionally persist ``advanced_tabs``."""
    from src.settings.ui_settings import save_settings

    cur = dict(getattr(win.settings, "advanced_tabs", None) or {})
    cur[str(tab_id)] = bool(advanced)
    win.settings = replace(win.settings, advanced_tabs=cur)
    if persist:
        try:
            save_settings(win.settings)
        except Exception:
            pass


class BasicAdvancedHeader(QWidget):
    """Top-right Basic | Advanced segmented control for a settings tab."""

    def __init__(
        self,
        tab_id: str,
        *,
        initial_advanced: bool = False,
        on_changed: Callable[[bool], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tab_id = tab_id
        self._on_changed = on_changed

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addStretch(1)

        self._picker = SegmentedPicker(
            [
                SegmentOption("Basic", "basic", tooltip="Essential controls only."),
                SegmentOption("Advanced", "advanced", tooltip="Full controls for power users."),
            ],
            accessible_name=f"{tab_id} mode",
            object_name_root=f"BasicAdvanced_{tab_id}",
            object_name_shell=f"BasicAdvancedShell_{tab_id}",
            min_button_width=72,
            min_button_height=28,
            font_size_px=12,
            default_index=1 if initial_advanced else 0,
        )
        self._picker.currentIndexChanged.connect(self._emit_mode)
        lay.addWidget(self._picker, 0)

    def _emit_mode(self, _index: int) -> None:
        if callable(self._on_changed):
            self._on_changed(self.is_advanced())

    def is_advanced(self) -> bool:
        return self._picker.currentData() == "advanced"

    def set_advanced(self, advanced: bool) -> None:
        self._picker.setCurrentIndex(1 if advanced else 0)


def attach_basic_advanced_header(
    win,
    tab_id: str,
    *,
    title_row_parent_layout,
    title_widget: QLabel | None = None,
) -> BasicAdvancedHeader:
    """
    Insert a Basic|Advanced header on the same row as an optional title label.
    Wires persistence and ``win._tab_advanced_sections[tab_id]`` visibility lists.
    """
    initial = is_tab_advanced(win.settings, tab_id)
    header = BasicAdvancedHeader(tab_id, initial_advanced=initial)

    def _on_mode(advanced: bool) -> None:
        set_tab_advanced(win, tab_id, advanced)
        sections = getattr(win, "_tab_advanced_sections", {}).get(tab_id, [])
        for w in sections:
            if w is not None:
                w.setVisible(advanced)
        if hasattr(win, "_resize_to_current_tab"):
            try:
                win._resize_to_current_tab()
            except Exception:
                pass

    header._on_changed = _on_mode  # noqa: SLF001
    header._picker.currentIndexChanged.connect(lambda _: _on_mode(header.is_advanced()))

    if title_widget is not None:
        row = QWidget()
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(8)
        row_lay.addWidget(title_widget, 1)
        row_lay.addWidget(header, 0)
        title_row_parent_layout.addWidget(row)
    else:
        title_row_parent_layout.addWidget(header)

    # Apply initial visibility
    _on_mode(initial)
    return header


def register_advanced_sections(win, tab_id: str, widgets: Iterable[QWidget]) -> None:
    """Register widgets shown only in Advanced mode for a tab."""
    store = getattr(win, "_tab_advanced_sections", None)
    if store is None:
        store = {}
        win._tab_advanced_sections = store
    store[tab_id] = list(widgets)
    advanced = is_tab_advanced(win.settings, tab_id)
    for w in widgets:
        if w is not None:
            w.setVisible(advanced)
