"""Character profile card for the Characters tab list."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from UI.theme import token
from src.content.characters_store import Character, character_reference_image_resolved

_CARD_HEIGHT = 92
_AVATAR_SIZE = 72


class CharacterCard(QFrame):
    """Avatar + name row; click to select. Expands to the list column width."""

    selected = pyqtSignal(str)

    def __init__(self, character: Character, *, is_selected: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._char_id = str(character.id)
        self.setObjectName("CharacterCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(_CARD_HEIGHT)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed))
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

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(12)

        self._avatar = QLabel()
        self._avatar.setFixedSize(_AVATAR_SIZE, _AVATAR_SIZE)
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar.setStyleSheet(
            f"background: rgba(255,255,255,0.04); border: 1px solid {border}; border-radius: 36px; color: {muted};"
        )
        p = character_reference_image_resolved(character)
        if p is not None and p.exists():
            pm = QPixmap(str(p))
            if not pm.isNull():
                self._avatar.setPixmap(
                    pm.scaled(
                        _AVATAR_SIZE,
                        _AVATAR_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self._avatar.setText("")
            else:
                self._avatar.setText("?")
        else:
            initials = (character.name or "?")[:1].upper()
            self._avatar.setText(initials)
        root.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)

        name = QLabel(character.name or "Unnamed")
        name.setWordWrap(True)
        name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        name.setStyleSheet(f"color: {text_c}; font-size: 13px; font-weight: 700;")
        name.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))
        text_col.addWidget(name)

        snippet = (character.identity or character.visual_style or "").strip().replace("\n", " ")
        if len(snippet) > 120:
            snippet = snippet[:117].rstrip() + "..."
        sub = QLabel(snippet or "No description yet")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        sub.setStyleSheet(f"color: {muted}; font-size: 11px;")
        sub.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
        text_col.addWidget(sub, 1)

        root.addLayout(text_col, 1)

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
