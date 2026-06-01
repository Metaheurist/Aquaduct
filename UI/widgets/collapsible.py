"""Reusable collapsible "Advanced" section for progressive disclosure in dense tabs."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QToolButton, QVBoxLayout, QWidget

from UI.theme import token


class CollapsibleSection(QWidget):
    """
    Header toggle + collapsible content body. Add widgets to ``content_layout``.

    Used to hide advanced/rarely-changed controls behind a single click so the common path
    stays uncluttered. Collapsed by default unless ``expanded=True``.
    """

    def __init__(
        self,
        title: str = "Advanced",
        *,
        expanded: bool = False,
        on_toggled=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._on_toggled = on_toggled

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._toggle = QToolButton()
        self._toggle.setCheckable(True)
        self._toggle.setChecked(bool(expanded))
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setAutoRaise(True)
        self._toggle.setStyleSheet(
            f"QToolButton {{ color: {token('muted', '#9BA6B8')}; font-size: 12px; "
            "font-weight: 700; border: none; padding: 2px 0; text-align: left; }"
        )
        self._toggle.toggled.connect(self._on_toggle)
        root.addWidget(self._toggle)

        self._content = QWidget()
        self.content_layout = QVBoxLayout(self._content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)
        root.addWidget(self._content)

        self._content.setVisible(bool(expanded))
        self._sync_header_text()

    def _sync_header_text(self) -> None:
        from PyQt6.QtCore import QSize
        from UI.widgets.toolbar_svg_icons import qicon_toolbar

        kind = "chevron_down" if self._toggle.isChecked() else "chevron_right"
        self._toggle.setIcon(qicon_toolbar(kind, token("muted", "#9BA6B8"), 14))
        self._toggle.setIconSize(QSize(14, 14))
        self._toggle.setText(f"  {self._title}")

    def _on_toggle(self, checked: bool) -> None:
        self._content.setVisible(checked)
        self._sync_header_text()
        if callable(self._on_toggled):
            try:
                self._on_toggled(checked)
            except Exception:
                pass

    def addWidget(self, w: QWidget) -> None:
        self.content_layout.addWidget(w)

    def setContentLayout(self, layout) -> None:
        self.content_layout.addLayout(layout)
