"""Side-by-side column helper for tab layouts."""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QWidget


def two_column_row(
    left: QWidget,
    right: QWidget,
    *,
    ratio: tuple[int, int] = (1, 1),
    spacing: int = 12,
    parent: QWidget | None = None,
) -> QWidget:
    """
    Return a widget with *left* and *right* children in a horizontal split.

    Stretch factors follow *ratio* (default 50/50).
    """
    row = QWidget(parent)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(int(spacing))
    left_stretch, right_stretch = ratio
    lay.addWidget(left, max(1, int(left_stretch)))
    lay.addWidget(right, max(1, int(right_stretch)))
    return row
