from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PreviewDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        title: str,
        personality_id: str,
        confidence: str = "",
        hook: str,
        segments: list[dict[str, str]],
        cta: str,
        on_regenerate: Callable[[], None],
        on_approve_run: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Preview")
        self.setMinimumSize(980, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = QLabel("Preview (script + storyboard)")
        header.setStyleSheet("font-size: 16px; font-weight: 800;")
        root.addWidget(header)

        conf_line = f"<br><b>Confidence</b>: {confidence}" if confidence else ""
        meta = QLabel(f"<b>Title</b>: {title}<br><b>Personality</b>: {personality_id}{conf_line}")
        meta.setWordWrap(True)
        meta.setStyleSheet("color: #B7B7C2;")
        root.addWidget(meta)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(8, 8, 8, 8)
        il.setSpacing(10)

        if hook.strip():
            hook_lbl = QLabel(f"<b>Hook</b><br>{hook}")
            hook_lbl.setWordWrap(True)
            hook_lbl.setStyleSheet("padding: 10px; border: 1px solid #3A3A44; border-radius: 10px;")
            il.addWidget(hook_lbl)

        for i, s in enumerate(segments or [], start=1):
            narration = (s.get("narration") or "").strip()
            visual = (s.get("visual_prompt") or "").strip()
            on_screen = (s.get("on_screen_text") or "").strip()
            parts: list[str] = [f"<b>Beat {i}</b>"]
            if on_screen:
                parts.append(f"<b>On-screen</b>: {on_screen}")
            if narration:
                parts.append(f"<b>Narration</b>: {narration}")
            if visual:
                parts.append(f"<b>Visual prompt</b>: {visual}")
            card = QLabel("<br>".join(parts))
            card.setWordWrap(True)
            card.setStyleSheet("padding: 10px; border: 1px solid #3A3A44; border-radius: 10px;")
            il.addWidget(card)

        if cta.strip():
            cta_lbl = QLabel(f"<b>CTA</b><br>{cta}")
            cta_lbl.setWordWrap(True)
            cta_lbl.setStyleSheet("padding: 10px; border: 1px solid #3A3A44; border-radius: 10px;")
            il.addWidget(cta_lbl)

        il.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        btns = QHBoxLayout()
        regen = QPushButton("Regenerate")
        regen.clicked.connect(on_regenerate)
        btns.addWidget(regen)

        approve = QPushButton("Approve & Run")
        approve.setObjectName("primary")
        approve.clicked.connect(on_approve_run)
        btns.addWidget(approve)

        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        btns.addWidget(close)

        btns.addStretch(1)
        root.addLayout(btns)

