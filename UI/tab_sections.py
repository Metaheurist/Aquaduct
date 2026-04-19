"""Reusable section titles and vertical spacing for settings tabs (dark theme)."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QVBoxLayout

# Gap between major blocks (below previous section’s last row).
SECTION_SPACING_PX = 18


def section_title(text: str, *, emphasis: bool = False) -> QLabel:
    """Muted subsection label (emphasis = slightly larger for major breaks)."""
    lab = QLabel(text)
    if emphasis:
        lab.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #E8E8EE; margin: 0; padding: 0 0 4px 0;"
        )
    else:
        lab.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #9BA6B8; margin: 0; padding: 0 0 2px 0;"
        )
    return lab


def add_section_spacing(layout: QVBoxLayout, *, px: int = SECTION_SPACING_PX) -> None:
    layout.addSpacing(px)
