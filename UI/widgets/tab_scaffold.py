from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from UI.widgets.tab_layout import apply_tab_page_layout
from UI.widgets.tab_layout import SECTION_CARD_MARGINS, SECTION_CARD_SPACING
from UI.widgets.tab_sections import section_card


def make_tab_root(
    *,
    title: str | None = None,
    intro_text: str | None = None,
    intro_tooltip: str | None = None,
    intro_stylesheet: str | None = None,
    before_card: Iterable[QWidget] | None = None,
    body_card: bool = True,
    fill_vertical: bool = False,
) -> tuple[QWidget, QVBoxLayout, QWidget, QVBoxLayout]:
    """
    Standard scroll-host layout for settings-style tabs: outer vertical layout, optional header,
    optional intro, optional widgets before the main body, then a body area for section content.

    When *body_card* is True (default), body widgets sit inside one ``section_card`` wrapper (API, Run, …).
    When False, widgets go on the body layout directly (Library side-by-side panels).

    Set *fill_vertical* so the body area expands to consume remaining tab height.

    Returns ``(root, outer_lay, body_host, body_lay)`` where widgets go on ``body_lay``.
    """
    root = QWidget()
    outer = QVBoxLayout(root)
    apply_tab_page_layout(outer)

    if title:
        hdr = QLabel(title)
        hdr.setStyleSheet("font-size: 16px; font-weight: 700; margin: 0; padding: 0 0 2px 0;")
        outer.addWidget(hdr)
    if intro_text:
        hint = QLabel(intro_text)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            intro_stylesheet or "color: #B7B7C2; font-size: 12px; margin: 0; padding: 0 0 4px 0;"
        )
        if intro_tooltip:
            hint.setToolTip(intro_tooltip)
        outer.addWidget(hint)
    if before_card:
        for wid in before_card:
            outer.addWidget(wid)

    body_host = QWidget()
    body_outer = QVBoxLayout(body_host)
    body_outer.setContentsMargins(0, 0, 0, 0)
    body_outer.setSpacing(0)

    if body_card:
        card, inner = section_card(margins=SECTION_CARD_MARGINS, spacing=SECTION_CARD_SPACING)
        body_outer.addWidget(card, 1 if fill_vertical else 0)
        body_lay = inner
    else:
        body_lay = body_outer
        body_lay.setSpacing(SECTION_CARD_SPACING)

    stretch = 1 if fill_vertical else 0
    outer.addWidget(body_host, stretch)
    return root, outer, body_host, body_lay
