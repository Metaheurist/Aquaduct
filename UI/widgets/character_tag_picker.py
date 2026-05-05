from __future__ import annotations

from functools import partial

from PyQt6.QtCore import QModelIndex, QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.content.characters_store import Character


class CharacterTagPicker(QWidget):
    """Ordered multi-select for Run-tab characters; first row is Lead (voice + portrait reference)."""

    orderChanged = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._catalog: dict[str, Character] = {}
        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.setMinimumHeight(72)
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._list.model().rowsMoved.connect(self._on_rows_moved)  # type: ignore[attr-defined]
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._ctx_menu)

        self._add_btn = QPushButton("Add character…")
        self._add_btn.clicked.connect(self._on_add_clicked)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._list, 1)
        row.addWidget(self._add_btn, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(row)

    def _on_rows_moved(
        self,
        parent: QModelIndex,
        start: int,
        end: int,
        destination: QModelIndex,
        row: int,
    ) -> None:
        del parent, start, end, destination, row
        self._decorate_lead()
        self.orderChanged.emit()

    def _decorate_lead(self) -> None:
        for i in range(self._list.count()):
            it = self._list.item(i)
            cid = str(it.data(Qt.ItemDataRole.UserRole) or "")
            ch = self._catalog.get(cid)
            name = ch.name if ch else cid[:8]
            label = f"Lead — {name}" if i == 0 else name
            it.setText(label)

    def get_ordered_ids(self) -> list[str]:
        out: list[str] = []
        for i in range(self._list.count()):
            it = self._list.item(i)
            cid = str(it.data(Qt.ItemDataRole.UserRole) or "").strip()
            if cid:
                out.append(cid)
        return out

    def set_state(self, *, characters: list[Character], selected_ids: list[str]) -> None:
        self._catalog = {c.id: c for c in characters}
        self._list.clear()
        seen: set[str] = set()
        for cid in selected_ids:
            cid = str(cid or "").strip()
            if not cid or cid in seen or cid not in self._catalog:
                continue
            seen.add(cid)
            self._append_item(cid)
        self._decorate_lead()

    def _append_item(self, cid: str) -> None:
        ch = self._catalog.get(cid)
        label = ch.name if ch else cid[:8]
        it = QListWidgetItem(label)
        it.setData(Qt.ItemDataRole.UserRole, cid)
        self._list.addItem(it)

    def _ctx_menu(self, pos: QPoint) -> None:
        it = self._list.itemAt(pos)
        if it is None:
            return
        menu = QMenu(self)
        rm = menu.addAction("Remove from run…")
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen == rm:
            self._list.takeItem(self._list.row(it))
            self._decorate_lead()
            self.orderChanged.emit()

    def _on_add_clicked(self) -> None:
        current = set(self.get_ordered_ids())
        menu = QMenu(self)
        any_opt = False
        for c in sorted(self._catalog.values(), key=lambda x: x.name.lower()):
            if c.id in current:
                continue
            any_opt = True
            act = menu.addAction(c.name)
            act.triggered.connect(partial(self._add_by_id, c.id))
        if not any_opt:
            menu.addAction("(All characters added)").setEnabled(False)
        menu.exec(self._add_btn.mapToGlobal(self._add_btn.rect().bottomLeft()))

    def _add_by_id(self, cid: str) -> None:
        if cid not in self._catalog or cid in self.get_ordered_ids():
            return
        self._append_item(cid)
        self._decorate_lead()
        self.orderChanged.emit()
