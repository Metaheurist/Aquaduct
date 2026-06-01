"""Reusable section titles and vertical spacing for settings tabs (dark theme)."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from UI.theme import token

StatusGlyphKind = str  # "check" | "cross" | "dot" | "half" | "warning" | "info"

_STATUS_COLOR: dict[str, str] = {
    "check": "accent",
    "cross": "danger",
    "dot": "muted",
    "half": "muted",
    "warning": "danger",
    "info": "muted",
}

# Gap between major blocks (below previous section’s last row).
SECTION_SPACING_PX = 18


def section_card(*, margins: int = 12, spacing: int = 10) -> tuple[QFrame, QVBoxLayout]:
    """
    Rounded container (``QFrame#SettingsSectionCard``) for a logical block inside a tab.
    Styled in ``UI/theme.py`` using the ``card`` palette token so it sits above the tab pane.
    """
    frame = QFrame()
    frame.setObjectName("SettingsSectionCard")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    return frame, lay


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


def section_title_with_help(
    text: str,
    topic_id: str,
    *,
    slide: int | None = None,
    emphasis: bool = False,
    on_open: Callable[[str, int | None], None] | None = None,
) -> QWidget:
    """
    Section title plus a small ``?`` glyph that deep-links into the Help tutorial.

    The glyph carries a rich ``help_tooltip_rich`` tooltip (hover) and, when ``on_open`` is
    given, clicking opens the matching tutorial topic/slide. Returns a row widget to add to a
    layout. Makes Help affordances visible instead of hover-only.
    """
    from UI.help.tutorial_links import help_tooltip_rich

    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.addWidget(section_title(text, emphasis=emphasis), 0)
    glyph = QToolButton()
    glyph.setText("?")
    glyph.setCursor(Qt.CursorShape.PointingHandCursor)
    glyph.setAutoRaise(True)
    accent = token("accent", "#25F4EE")
    border = token("border", "#23232B")
    glyph.setStyleSheet(
        "QToolButton { color: %s; border: 1px solid %s; border-radius: 9px; "
        "font-weight: 800; font-size: 11px; padding: 0; }"
        "QToolButton:hover { border: 1px solid %s; }" % (accent, border, accent)
    )
    glyph.setFixedSize(18, 18)
    glyph.setToolTip(help_tooltip_rich("Open Help for this section.", topic_id, slide=slide))
    glyph.setAccessibleName(f"Help: {text}")
    if on_open is not None:
        glyph.clicked.connect(lambda: on_open(topic_id, slide))
    lay.addWidget(glyph, 0)
    lay.addStretch(1)
    return row


def empty_state_panel(
    message: str,
    *,
    title: str | None = None,
    action_text: str | None = None,
    on_action: Callable[[], None] | None = None,
) -> QFrame:
    """
    Shared 'no data yet' placeholder used by output/content tabs and dialog previews.

    Palette-styled dashed panel with an optional headline, body message, and a single action
    button (e.g. "Go to Pipeline"). Hidden/shown by callers based on whether data exists.
    """
    panel = QFrame()
    panel.setObjectName("EmptyStatePanel")
    border = token("border", "#23232B")
    muted = token("muted", "#B7B7C2")
    text_c = token("text", "#FFFFFF")
    panel.setStyleSheet(
        "QFrame#EmptyStatePanel { border: 1px dashed %s; border-radius: 12px; "
        "background-color: rgba(255,255,255,0.02); }" % border
    )
    lay = QVBoxLayout(panel)
    lay.setContentsMargins(20, 22, 20, 22)
    lay.setSpacing(8)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if title:
        head = QLabel(title)
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.setStyleSheet(f"color: {text_c}; font-size: 14px; font-weight: 700;")
        lay.addWidget(head)
    body = QLabel(message)
    body.setWordWrap(True)
    body.setAlignment(Qt.AlignmentFlag.AlignCenter)
    body.setStyleSheet(f"color: {muted}; font-size: 12px;")
    lay.addWidget(body)
    if action_text and on_action is not None:
        btn = QPushButton(action_text)
        btn.setProperty("buttonRole", "secondary")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(on_action)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn, 0)
        row.addStretch(1)
        lay.addLayout(row)
    return panel


def dialog_subtitle_label(text: str) -> QLabel:
    """Muted 12px subtitle line shared by dialogs (palette-aware)."""
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet(f"color: {token('muted', '#9BA6B8')}; font-size: 12px;")
    return lab


def dialog_status_label(text: str = "") -> QLabel:
    """Muted 11px status line shared by dialogs (palette-aware)."""
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet(f"color: {token('muted', '#B7B7C2')}; font-size: 11px;")
    return lab


def status_glyph_label(
    kind: StatusGlyphKind,
    text: str,
    *,
    color_token: str | None = None,
    icon_size: int = 14,
) -> QWidget:
    """
    Small SVG icon + label row for status badges (replaces unicode checkmarks/warnings).

    *kind* maps to toolbar SVG icons: check, cross, dot, half, warning, info.
    """
    from UI.widgets.toolbar_svg_icons import ToolbarIconKind, pixmap_toolbar

    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    tok = color_token or _STATUS_COLOR.get(kind, "muted")
    color = token(tok, "#B7B7C2")
    icon_lbl = QLabel()
    icon_lbl.setFixedSize(icon_size, icon_size)
    pm: QPixmap = pixmap_toolbar(kind, color, size=icon_size)  # type: ignore[arg-type]
    if not pm.isNull():
        icon_lbl.setPixmap(pm)
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(icon_lbl, 0)
    text_lbl = QLabel(text)
    text_lbl.setWordWrap(True)
    text_lbl.setStyleSheet(f"color: {color}; font-size: 12px;")
    lay.addWidget(text_lbl, 1)
    return row


def status_glyph_set_text(row: QWidget, text: str, *, kind: StatusGlyphKind | None = None, color_token: str | None = None) -> None:
    """Update an existing ``status_glyph_label`` row's text (and optionally icon/color)."""
    from UI.widgets.toolbar_svg_icons import pixmap_toolbar

    lay = row.layout()
    if lay is None or lay.count() < 2:
        return
    icon_w = lay.itemAt(0).widget()
    text_w = lay.itemAt(1).widget()
    if kind is not None and icon_w is not None:
        tok = color_token or _STATUS_COLOR.get(kind, "muted")
        color = token(tok, "#B7B7C2")
        pm = pixmap_toolbar(kind, color, size=14)  # type: ignore[arg-type]
        if isinstance(icon_w, QLabel) and not pm.isNull():
            icon_w.setPixmap(pm)
        if isinstance(text_w, QLabel):
            text_w.setStyleSheet(f"color: {color}; font-size: 12px;")
    if isinstance(text_w, QLabel):
        text_w.setText(text)
