"""Selectable project card with thumbnail for the Library tab."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

from UI.theme import token
from UI.widgets.tile_svg_icons import pixmap_tile


class LibraryProjectCard(QFrame):
    """Portrait card: thumbnail, title, folder + meta. Single-click selects, double-click opens folder."""

    clicked = pyqtSignal()
    doubleClicked = pyqtSignal()

    _THUMB_W = 132
    _THUMB_H = 176

    def __init__(
        self,
        *,
        title: str,
        folder_name: str,
        meta: str,
        project_path: Path,
        thumbnail_path: Path | None = None,
        photo: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._project_path = project_path.resolve()
        self._selected = False
        self.setObjectName("LibraryProjectCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(148)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self._thumb = QLabel()
        self._thumb.setFixedSize(self._THUMB_W, self._THUMB_H)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setScaledContents(True)
        self._set_thumbnail(thumbnail_path, photo=photo)
        lay.addWidget(self._thumb, 0, Qt.AlignmentFlag.AlignHCenter)

        title_lbl = QLabel(title[:120])
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet("color: #E8E8EE; font-size: 12px; font-weight: 700;")
        lay.addWidget(title_lbl)

        folder_lbl = QLabel(folder_name[:80])
        folder_lbl.setStyleSheet("color: #8A96A3; font-size: 10px;")
        folder_lbl.setWordWrap(True)
        lay.addWidget(folder_lbl)

        meta_lbl = QLabel(meta)
        meta_lbl.setStyleSheet("color: #9BA6B8; font-size: 10px;")
        lay.addWidget(meta_lbl)

        self._apply_palette()

    def _set_thumbnail(self, thumbnail_path: Path | None, *, photo: bool) -> None:
        border = token("border", "#2E2E38")
        panel = token("panel", "#0B0B0F")
        if thumbnail_path is not None and thumbnail_path.is_file():
            pm = QPixmap(str(thumbnail_path))
            if not pm.isNull():
                self._thumb.setPixmap(
                    pm.scaled(
                        self._THUMB_W,
                        self._THUMB_H,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self._thumb.setStyleSheet(
                    f"background-color: {panel}; border: 1px solid {border}; border-radius: 8px;"
                )
                return
        icon = "image" if photo else "phone_vertical"
        ph = pixmap_tile(icon, token("muted", "#6A6A78"), 40)
        self._thumb.setPixmap(ph)
        self._thumb.setStyleSheet(
            f"background-color: {panel}; border: 1px dashed {border}; border-radius: 8px;"
        )

    def project_path(self) -> Path:
        return self._project_path

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._apply_palette()

    def is_selected(self) -> bool:
        return self._selected

    def _apply_palette(self) -> None:
        border = token("border", "#2E2E38")
        accent = token("accent", "#25F4EE")
        bg = "rgba(37, 244, 238, 0.06)" if self._selected else "transparent"
        b = accent if self._selected else border
        self.setStyleSheet(
            f"QFrame#LibraryProjectCard {{ background-color: {bg}; border: 2px solid {b}; border-radius: 12px; }}"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)
