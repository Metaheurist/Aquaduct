"""Shared margins and spacing for tab page layouts."""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout

# Outer tab page (inside QTabWidget pane, below tab bar).
TAB_PAGE_MARGINS = (16, 14, 16, 16)
TAB_PAGE_SPACING = 12

# Section cards inside tabs.
SECTION_CARD_MARGINS = 16
SECTION_CARD_SPACING = 12


def apply_tab_page_layout(layout: QVBoxLayout) -> None:
    """Standard outer margins/spacing for tab scroll content."""
    layout.setContentsMargins(*TAB_PAGE_MARGINS)
    layout.setSpacing(TAB_PAGE_SPACING)
