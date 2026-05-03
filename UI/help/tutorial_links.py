"""
HTML tooltips with clickable links that open the in-app Help dialog on a topic/slide.

Native Qt tooltips cannot reliably receive clicks; RichHelpTooltipFilter intercepts
ToolTip events when the effective tooltip text is HTML containing topic:// URLs
(including QAbstractItemView rows where the text lives on ``ToolTipRole``) and
shows a small QTextBrowser popup instead.
"""

from __future__ import annotations

import html
from collections.abc import Callable

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt, QUrl, QUrlQuery
from PyQt6.QtGui import QCursor, QHelpEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFrame,
    QTextBrowser,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from UI.dialogs.tutorial_dialog import TUTORIAL_TOPICS

TUTORIAL_TOPIC_IDS: tuple[str, ...] = tuple(t.topic_id for t in TUTORIAL_TOPICS)


def topic_index_by_id(topic_id: str) -> int | None:
    for i, t in enumerate(TUTORIAL_TOPICS):
        if t.topic_id == topic_id:
            return i
    return None


def help_tooltip_rich(
    base_plain: str,
    topic_id: str,
    *,
    link_label: str = "Open in Help →",
    slide: int | None = None,
) -> str:
    """
    Build an HTML tooltip with a link of the form topic://<topic_id>?slide=N.

    ``base_plain`` is escaped; newlines become <br/>.
    If ``slide`` is None, slide 0 is used (query omitted for clarity - dialog defaults to 0).
    """
    safe = html.escape(base_plain).replace("\n", "<br/>")
    qslide = 0 if slide is None else slide
    href = f"topic://{topic_id}?slide={qslide}"
    lbl = html.escape(link_label)
    return (
        f'<html><body style="color:#C8C8D4;font-size:12px;">{safe}<br/><br/>'
        f'<a href="{href}" style="color:#6EC8FF;text-decoration:none;">{lbl}</a>'
        f"</body></html>"
    )


def help_tooltip_rich_unless_already(
    base_plain: str,
    topic_id: str,
    *,
    link_label: str = "Open in Help →",
    slide: int | None = None,
) -> str:
    """
    Build ``help_tooltip_rich(...)`` for plain text, or return ``base_plain`` unchanged if it is
    already a wrapped help tooltip.

    Use when copying ``Qt.ItemDataRole.ToolTipRole`` from a model item onto a widget: those items
    often already store the full ``<html>…topic://…`` string; wrapping again escapes the inner HTML
    so the user sees literal tags in the tooltip.
    """
    t = (base_plain or "").strip()
    tl = t.lower()
    if tl.startswith("<html") and "topic://" in t:
        return t
    return help_tooltip_rich(t, topic_id, link_label=link_label, slide=slide)


def _rich_help_tooltip_text(widget: QWidget, event: QEvent) -> str:
    """
    Return tooltip HTML for ``widget`` + ``event``.

    ``QComboBox`` list rows (and similar views) store rich text on the model's ``ToolTipRole`` while
    the hover target is often the *viewport* with an empty ``QWidget.toolTip()`` - resolve that here.
    """
    direct = (widget.toolTip() or "").strip()
    if direct:
        return widget.toolTip()

    if isinstance(event, QHelpEvent):
        gpos = event.globalPos()
    else:
        gpos = QCursor.pos()

    view: QAbstractItemView | None = widget if isinstance(widget, QAbstractItemView) else None
    p = widget.parentWidget()
    while p is not None and view is None:
        if isinstance(p, QAbstractItemView):
            view = p
            break
        p = p.parentWidget()
    if view is None:
        return ""

    vp = view.viewport()
    local = vp.mapFromGlobal(gpos)
    idx = view.indexAt(local)
    if not idx.isValid():
        return ""
    data = idx.data(Qt.ItemDataRole.ToolTipRole)
    return str(data) if data else ""


def _parse_topic_url(url: QUrl) -> tuple[str, int] | None:
    if url.scheme() != "topic":
        return None
    host = (url.host() or "").strip()
    if not host:
        return None
    slide_s = QUrlQuery(url.query()).queryItemValue("slide")
    try:
        slide = int(slide_s) if slide_s else 0
    except ValueError:
        slide = 0
    return host, max(0, slide)


class _RichHelpTooltipPopup(QFrame):
    """Frameless popup with one clickable help link."""

    def __init__(
        self,
        html_body: str,
        on_open: Callable[[str, int], None],
        parent: QWidget | None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(
            "QFrame { background-color: #14141A; border: 1px solid #2A2A34; border-radius: 8px; }"
        )
        self._on_open = on_open

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        br = QTextBrowser()
        br.setOpenExternalLinks(False)
        br.setOpenLinks(False)
        br.setFrameShape(QFrame.Shape.NoFrame)
        br.setHtml(html_body)
        br.setFixedWidth(400)
        br.document().setTextWidth(380)
        br.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        br.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        br.setStyleSheet(
            "QTextBrowser { background-color: transparent; color: #C8C8D4; font-size: 12px; padding: 4px; }"
        )
        h = int(br.document().size().height()) + 24
        br.setFixedHeight(min(max(h, 80), 360))
        br.anchorClicked.connect(self._on_anchor)
        lay.addWidget(br)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close)

    def _on_anchor(self, url: QUrl) -> None:
        parsed = _parse_topic_url(url)
        if parsed is None:
            return
        tid, slide = parsed
        self.close()
        self._on_open(tid, slide)


class RichHelpTooltipFilter(QObject):
    """
    Install on QApplication. When the effective tooltip is HTML containing topic://,
    suppress the native tooltip and show a clickable popup instead.
    """

    def __init__(self, on_open_help: Callable[[str, int], None], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._on_open_help = on_open_help
        self._popup: QWidget | None = None

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if event.type() != QEvent.Type.ToolTip:
            return False
        if not isinstance(obj, QWidget):
            return False
        tip = _rich_help_tooltip_text(obj, event)
        if not tip:
            return False
        stripped = tip.strip()
        if not stripped.lower().startswith("<html"):
            return False
        if "topic://" not in tip:
            return False
        if isinstance(event, QHelpEvent):
            gpos = event.globalPos()
        else:
            gpos = QCursor.pos()
        QToolTip.hideText()
        self._show_popup(tip, gpos, obj)
        return True

    def _show_popup(self, html_body: str, global_pos: QPoint, anchor: QWidget) -> None:
        if self._popup is not None:
            try:
                self._popup.close()
            except Exception:
                pass
            self._popup = None
        parent_win = anchor.window()
        pop = _RichHelpTooltipPopup(html_body, self._on_open_help, parent_win)
        self._popup = pop
        pop.destroyed.connect(self._on_popup_destroyed)
        g = global_pos + QPoint(12, 8)
        # Keep on screen (rough)
        screen = QApplication.screenAt(g)
        if screen is not None:
            geo = screen.availableGeometry()
            ph = pop.sizeHint().height()
            pw = pop.sizeHint().width()
            if g.x() + pw > geo.right():
                g.setX(max(geo.left(), geo.right() - pw - 8))
            if g.y() + ph > geo.bottom():
                g.setY(max(geo.top(), global_pos.y() - ph - 8))
        pop.move(g)
        pop.show()

    def _on_popup_destroyed(self, *_args: object) -> None:
        self._popup = None
