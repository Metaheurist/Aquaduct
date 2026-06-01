"""Character profile card for the Characters tab grid."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from UI.theme import token
from src.content.characters_store import Character, character_reference_image_resolved


class CharacterCard(QFrame):
    """Avatar + name card; click to select."""

    selected = pyqtSignal(str)

    def __init__(self, character: Character, *, is_selected: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._char_id = str(character.id)
        self.setObjectName("CharacterCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(132)
        accent = token("accent", "#25F4EE")
        border = token("border", "#23232B")
        muted = token("muted", "#B7B7C2")
        text_c = token("text", "#FFFFFF")
        self._style_selected = (
            f"QFrame#CharacterCard {{ background: rgba(37,244,238,0.08); border: 1px solid {accent}; "
            f"border-radius: 14px; }}"
        )
        self._style_normal = (
            f"QFrame#CharacterCard {{ background: rgba(255,255,255,0.03); border: 1px solid {border}; "
            f"border-radius: 14px; }}"
            f"QFrame#CharacterCard:hover {{ border: 1px solid {accent}; }}"
        )
        self.setStyleSheet(self._style_selected if is_selected else self._style_normal)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._avatar = QLabel()
        self._avatar.setFixedSize(64, 64)
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar.setStyleSheet(
            f"background: rgba(255,255,255,0.04); border: 1px solid {border}; border-radius: 32px; color: {muted};"
        )
        p = character_reference_image_resolved(character)
        if p is not None and p.exists():
            pm = QPixmap(str(p))
            if not pm.isNull():
                self._avatar.setPixmap(
                    pm.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                )
                self._avatar.setText("")
            else:
                self._avatar.setText("?")
        else:
            initials = (character.name or "?")[:1].upper()
            self._avatar.setText(initials)
        lay.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignHCenter)

        name = QLabel((character.name or "Unnamed")[:24])
        name.setWordWrap(True)
        name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        name.setStyleSheet(f"color: {text_c}; font-size: 12px; font-weight: 700;")
        lay.addWidget(name)

        snippet = (character.identity or character.visual_style or "").strip().replace("\n", " ")
        if len(snippet) > 48:
            snippet = snippet[:45] + "..."
        sub = QLabel(snippet or "No description yet")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        sub.setStyleSheet(f"color: {muted}; font-size: 10px;")
        lay.addWidget(sub)

    @property
    def char_id(self) -> str:
        return self._char_id

    def set_selected(self, on: bool) -> None:
        self.setStyleSheet(self._style_selected if on else self._style_normal)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._char_id)
            return
        super().mousePressEvent(event)
