from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from UI.widgets.tab_sections import section_card


def make_tab_root(
    *,
    title: str | None = None,
    intro_text: str | None = None,
    intro_tooltip: str | None = None,
    intro_stylesheet: str | None = None,
    before_card: Iterable[QWidget] | None = None,
) -> tuple[QWidget, QVBoxLayout, QWidget, QVBoxLayout]:
    """
    Standard scroll-host layout for settings-style tabs: outer vertical layout, optional header,
    optional intro, optional widgets before the main body card, then a card with inner body layout.

    Returns ``(root, outer_lay, body_host, body_lay)`` where widgets go on ``body_lay``.
    """
    root = QWidget()
    outer = QVBoxLayout(root)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    if title:
        hdr = QLabel(title)
        hdr.setStyleSheet("font-size: 16px; font-weight: 700;")
        outer.addWidget(hdr)
    if intro_text:
        hint = QLabel(intro_text)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            intro_stylesheet or "color: #B7B7C2; font-size: 12px; margin-bottom: 8px;"
        )
        if intro_tooltip:
            hint.setToolTip(intro_tooltip)
        outer.addWidget(hint)
    if before_card:
        for wid in before_card:
            outer.addWidget(wid)
    card, inner = section_card()
    outer.addWidget(card)
    return root, outer, card, inner
