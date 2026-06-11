"""Side-by-side column helper for tab layouts."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget


def two_column_row(
    left: QWidget,
    right: QWidget,
    *,
    ratio: tuple[int, int] = (1, 1),
    spacing: int = 16,
    parent: QWidget | None = None,
    equal_height: bool = True,
) -> QWidget:
    """
    Return a widget with *left* and *right* children in a horizontal split.

    Stretch factors follow *ratio* (default 50/50). When *equal_height* is True, both
    columns expand vertically to fill the row.
    """
    row = QWidget(parent)
    row.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(int(spacing))
    lay.setAlignment(Qt.AlignmentFlag.AlignTop)
    left_stretch, right_stretch = ratio
    if equal_height:
        for w in (left, right):
            w.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
    lay.addWidget(left, max(1, int(left_stretch)))
    lay.addWidget(right, max(1, int(right_stretch)))
    return row
