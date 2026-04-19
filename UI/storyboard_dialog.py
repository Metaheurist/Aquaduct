from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from UI.frameless_dialog import FramelessDialog, aquaduct_information, aquaduct_warning


class StoryboardPreviewDialog(FramelessDialog):
    def __init__(
        self,
        parent=None,
        *,
        manifest_path: Path,
        grid_png_path: Path,
        on_regenerate_all: Callable[[], None],
        on_approve_render: Callable[[], None],
    ) -> None:
        super().__init__(parent, title="Storyboard Preview")
        self.setMinimumSize(1020, 760)

        self.manifest_path = Path(manifest_path)
        self.grid_png_path = Path(grid_png_path)
        self._on_regen_all = on_regenerate_all
        self._on_approve_render = on_approve_render

        header = QLabel("Storyboard Preview (first-frame grid)")
        header.setStyleSheet("font-size: 16px; font-weight: 800;")
        self.body_layout.addWidget(header)

        self.meta = QLabel("")
        self.meta.setStyleSheet("color: #B7B7C2;")
        self.meta.setWordWrap(True)
        self.body_layout.addWidget(self.meta)

        self.grid_lbl = QLabel()
        self.grid_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grid_lbl.setStyleSheet("border: 1px solid #3A3A44; border-radius: 10px; padding: 6px;")
        self.body_layout.addWidget(self.grid_lbl, 1)

        # Controls
        controls = QHBoxLayout()
        self.scene_spin = QSpinBox()
        self.scene_spin.setRange(1, 12)
        controls.addWidget(QLabel("Scene #"))
        controls.addWidget(self.scene_spin)

        regen_all = QPushButton("Regenerate all")
        regen_all.clicked.connect(self._on_regen_all)
        controls.addWidget(regen_all)

        approve = QPushButton("Approve & Render")
        approve.setObjectName("primary")
        approve.clicked.connect(self._on_approve_render)
        controls.addWidget(approve)

        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        controls.addWidget(close)
        controls.addStretch(1)
        self.body_layout.addLayout(controls)

        # Scene editor
        self._editor = QWidget()
        form = QFormLayout(self._editor)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.prompt_edit = QLineEdit()
        form.addRow("Prompt", self.prompt_edit)

        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 2_000_000_000)
        form.addRow("Seed", self.seed_spin)

        save_scene = QPushButton("Save scene edits to manifest")
        save_scene.clicked.connect(self._save_scene_edits)
        form.addRow("", save_scene)

        self.body_layout.addWidget(self._editor, 0)

        self.scene_spin.valueChanged.connect(self._load_scene_into_editor)
        self.refresh()

    def refresh(self) -> None:
        try:
            m = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            m = {}
        title = str(m.get("title", "") or "")
        scenes = m.get("scenes", []) if isinstance(m, dict) else []
        n = len(scenes) if isinstance(scenes, list) else 0
        self.meta.setText(f"<b>Title</b>: {title}<br><b>Scenes</b>: {n}<br><b>Manifest</b>: {self.manifest_path}")
        self.scene_spin.setRange(1, max(1, n))
        self._load_scene_into_editor()

        try:
            if self.grid_png_path.exists():
                pm = QPixmap(str(self.grid_png_path))
                # Fit into dialog width reasonably
                pm = pm.scaledToWidth(980, Qt.TransformationMode.SmoothTransformation)
                self.grid_lbl.setPixmap(pm)
        except Exception:
            pass

    def _load_scene_into_editor(self) -> None:
        try:
            m = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            scenes = m.get("scenes", []) if isinstance(m, dict) else []
            idx = int(self.scene_spin.value()) - 1
            if not isinstance(scenes, list) or idx < 0 or idx >= len(scenes):
                return
            sc = scenes[idx] if isinstance(scenes[idx], dict) else {}
            self.prompt_edit.setText(str(sc.get("prompt", "") or ""))
            try:
                self.seed_spin.setValue(int(sc.get("seed", 0) or 0))
            except Exception:
                self.seed_spin.setValue(0)
        except Exception:
            pass

    def _save_scene_edits(self) -> None:
        try:
            m = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            scenes = m.get("scenes", []) if isinstance(m, dict) else []
            idx = int(self.scene_spin.value()) - 1
            if not isinstance(scenes, list) or idx < 0 or idx >= len(scenes):
                return
            sc = scenes[idx] if isinstance(scenes[idx], dict) else {}
            sc["prompt"] = str(self.prompt_edit.text()).strip()
            sc["seed"] = int(self.seed_spin.value())
            scenes[idx] = sc
            m["scenes"] = scenes
            self.manifest_path.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
            aquaduct_information(self, "Saved", "Scene updated in manifest.json")
        except Exception as e:
            aquaduct_warning(self, "Save failed", str(e))

