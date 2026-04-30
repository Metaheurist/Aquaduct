"""Modal-less frameless window: scrolling line charts for this process CPU/RAM and GPU VRAM."""

from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QPointF, QTimer, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from UI.dialogs.frameless_dialog import FramelessDialog
from UI.widgets.no_wheel_controls import NoWheelComboBox
from UI.widgets.title_bar_outline_button import styled_outline_button

from src.models.hardware import list_cuda_gpus
from src.util.resource_sample import sample_aquaduct_resources, sample_gpu_mem_pct

_HISTORY = 120  # 2 minutes at 1 Hz

_SPLIT_GPU_COLORS = ("#A78BFA", "#F472B6", "#34D399", "#FB923C", "#38BDF8", "#E879F9")


class _SparklineChart(QWidget):
    """Simple 0–100 time series drawn as a polyline."""

    def __init__(self, *, color: str, y_label: str = "0–100%") -> None:
        super().__init__()
        self._data: deque[float] = deque(maxlen=_HISTORY)
        self._color = QColor(color)
        self._y_label = y_label
        self.setMinimumHeight(96)
        self.setMinimumWidth(420)

    def push(self, value: float) -> None:
        self._data.append(max(0.0, min(100.0, value)))
        self.update()

    def clear_data(self) -> None:
        self._data.clear()
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        pad_l, pad_r, pad_t, pad_b = 44.0, 8.0, 8.0, 22.0
        inner_w = max(1.0, w - pad_l - pad_r)
        inner_h = max(1.0, h - pad_t - pad_b)

        # Grid
        painter.setPen(QPen(QColor("#2A2A33"), 1.0))
        for frac in (0.0, 0.5, 1.0):
            y = pad_t + inner_h * frac
            painter.drawLine(int(pad_l), int(y), int(pad_l + inner_w), int(y))

        painter.setPen(QColor("#6A7080"))
        painter.drawText(4, int(pad_t + 6), "100")
        painter.drawText(4, int(pad_t + inner_h // 2 + 4), "50")
        painter.drawText(4, int(pad_t + inner_h - 2), "0")

        n = len(self._data)
        if n < 2:
            painter.setPen(QColor("#8A96A3"))
            painter.drawText(int(pad_l + 8), int(pad_t + inner_h // 2), "Collecting samples…")
            return

        pts: list[tuple[float, float]] = []
        for i, v in enumerate(self._data):
            x = pad_l + inner_w * (i / max(1, n - 1))
            y = pad_t + inner_h * (1.0 - v / 100.0)
            pts.append((x, y))

        painter.setPen(QPen(self._color, 2.0))
        for i in range(1, len(pts)):
            painter.drawLine(int(pts[i - 1][0]), int(pts[i - 1][1]), int(pts[i][0]), int(pts[i][1]))

        # Fill under curve
        if len(pts) >= 2:
            poly = QPolygonF([QPointF(pts[0][0], pad_t + inner_h)] + [QPointF(a, b) for a, b in pts] + [QPointF(pts[-1][0], pad_t + inner_h)])
            c = QColor(self._color)
            c.setAlpha(45)
            painter.setBrush(QBrush(c))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(poly)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.setPen(QColor("#B7B7C2"))
        painter.drawText(int(pad_l), int(h - 4), f"{self._y_label}  •  window: last {n}s")


class ResourceGraphDialog(FramelessDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Resource usage")
        self.setModal(False)
        self.setMinimumWidth(520)
        self.setMinimumHeight(500)
        self._monitor_gpu_index = 0
        self._gpu_split_track: list[tuple[int, str, QLabel, _SparklineChart]] = []

        self._cpu_lbl = QLabel("CPU — —%")
        self._cpu_lbl.setStyleSheet("color: #25F4EE; font-weight: 700; font-size: 12px;")
        self.body_layout.addWidget(self._cpu_lbl)
        self._cpu_chart = _SparklineChart(color="#25F4EE", y_label="CPU % (÷ cores)")
        self.body_layout.addWidget(self._cpu_chart)

        self._ram_lbl = QLabel("RAM — —%")
        self._ram_lbl.setStyleSheet("color: #FFB703; font-weight: 700; font-size: 12px;")
        self.body_layout.addWidget(self._ram_lbl)
        self._ram_chart = _SparklineChart(color="#FFB703", y_label="RAM % of system")
        self.body_layout.addWidget(self._ram_chart)

        gpu_hdr = QHBoxLayout()
        self._gpu_lbl = QLabel("GPU VRAM —")
        self._gpu_lbl.setStyleSheet("color: #A78BFA; font-weight: 700; font-size: 12px;")
        gpu_hdr.addWidget(self._gpu_lbl)
        gpu_hdr.addStretch(1)
        self._gpu_monitor_combo = NoWheelComboBox()
        self._gpu_monitor_combo.setMinimumWidth(220)
        self._gpu_monitor_combo.setToolTip(
            "VRAM % for this CUDA device (process allocations). "
            "In Auto GPU policy, script (LLM) and image/video (diffusion) can use different GPUs — "
            "switch Monitor to compare. ~70–90% on the active GPU during a run is normal; the other GPU may show a lower flat line."
        )
        gpu_hdr.addWidget(QLabel("Monitor:"))
        gpu_hdr.addWidget(self._gpu_monitor_combo)
        self._split_chk = QCheckBox("Split view")
        self._split_chk.setToolTip(
            "Show a separate VRAM chart for each CUDA GPU (scroll if many devices). "
            "Turn off to use Monitor and a single chart."
        )
        self._split_chk.setStyleSheet("color: #B7B7C2; font-weight: 600; font-size: 12px;")
        self._split_chk.toggled.connect(self._on_split_toggled)
        gpu_hdr.addWidget(self._split_chk)
        self.body_layout.addLayout(gpu_hdr)
        self._gpu_chart = _SparklineChart(color="#A78BFA", y_label="VRAM % (CUDA)")
        self.body_layout.addWidget(self._gpu_chart)

        self._gpu_split_inner = QWidget()
        self._gpu_split_inner_layout = QVBoxLayout(self._gpu_split_inner)
        self._gpu_split_inner_layout.setContentsMargins(0, 4, 0, 0)
        self._gpu_split_inner_layout.setSpacing(0)
        self._gpu_split_scroll = QScrollArea()
        self._gpu_split_scroll.setWidgetResizable(True)
        self._gpu_split_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._gpu_split_scroll.setWidget(self._gpu_split_inner)
        self._gpu_split_scroll.setMinimumHeight(140)
        self._gpu_split_scroll.setVisible(False)
        self.body_layout.addWidget(self._gpu_split_scroll)

        purge_row = QHBoxLayout()
        branding = None
        try:
            par = parent
            if par is not None and hasattr(par, "settings"):
                branding = getattr(par.settings, "branding", None)
        except Exception:
            branding = None
        self._purge_btn = styled_outline_button("Purge memory", "accent_icon", min_width=132, branding=branding)
        self._purge_btn.setToolTip(
            "Run aggressive Python garbage collection and clear PyTorch CUDA cache on all GPUs "
            "(and MPS cache on Apple Silicon). Frees unreachable objects and returns allocator "
            "memory to the driver; it does **not** force-unload models still in use by a running job."
        )
        self._purge_btn.clicked.connect(self._on_purge_clicked)
        purge_row.addWidget(self._purge_btn)
        purge_row.addStretch(1)
        self._purge_status_lbl = QLabel("")
        self._purge_status_lbl.setStyleSheet("color: #8A96A3; font-size: 11px;")
        self._purge_status_lbl.setWordWrap(True)
        purge_row.addWidget(self._purge_status_lbl, 1)
        self.body_layout.addLayout(purge_row)

        self._gpu_monitor_combo.currentIndexChanged.connect(self._on_monitor_gpu_changed)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def _clear_split_gpu_panel(self) -> None:
        self._gpu_split_track.clear()
        while self._gpu_split_inner_layout.count():
            item = self._gpu_split_inner_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _rebuild_split_gpu_ui(self) -> None:
        self._clear_split_gpu_panel()
        gpus = list_cuda_gpus()
        specs: list[tuple[int, str]]
        if not gpus:
            specs = [(0, "GPU 0")]
        else:
            specs = [(int(g.index), f"{g.index}: {g.name}") for g in gpus]

        total_h = 0
        for i, (ix, title) in enumerate(specs):
            color = _SPLIT_GPU_COLORS[i % len(_SPLIT_GPU_COLORS)]
            lbl = QLabel(f"{title} — VRAM …")
            lbl.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 11px;")
            chart = _SparklineChart(color=color, y_label=f"GPU {ix} VRAM %")
            chart.setMinimumHeight(82)
            row = QWidget()
            vl = QVBoxLayout(row)
            vl.setContentsMargins(0, 0, 0, 10)
            vl.setSpacing(4)
            vl.addWidget(lbl)
            vl.addWidget(chart)
            self._gpu_split_inner_layout.addWidget(row)
            self._gpu_split_track.append((ix, title, lbl, chart))
            total_h += 96 + 82 + 10

        self._gpu_split_scroll.setMinimumHeight(min(420, max(140, total_h + 24)))

    def _apply_gpu_view_mode(self) -> None:
        split = self._split_chk.isChecked()
        self._gpu_monitor_combo.setEnabled(not split)
        self._gpu_lbl.setVisible(not split)
        self._gpu_chart.setVisible(not split)
        self._gpu_split_scroll.setVisible(split)
        if split:
            self._rebuild_split_gpu_ui()
        else:
            self._clear_split_gpu_panel()

    def _on_split_toggled(self, checked: bool) -> None:
        self._apply_gpu_view_mode()
        parent = self.parent()
        if parent is not None and hasattr(parent, "settings") and hasattr(parent, "_save_settings"):
            try:
                from dataclasses import replace

                from src.core.config import AppSettings

                cur = parent.settings
                if isinstance(cur, AppSettings):
                    parent.settings = replace(cur, resource_graph_split_view=bool(checked))
                    parent._save_settings()
            except Exception:
                pass

    def _populate_monitor_combo(self) -> None:
        self._gpu_monitor_combo.blockSignals(True)
        self._gpu_monitor_combo.clear()
        gpus = list_cuda_gpus()
        if not gpus:
            self._gpu_monitor_combo.addItem("GPU 0", 0)
            self._monitor_gpu_index = 0
        else:
            for g in gpus:
                self._gpu_monitor_combo.addItem(f"{g.index}: {g.name}", int(g.index))
        # Restore from main window settings
        parent = self.parent()
        want = 0
        try:
            if parent is not None and hasattr(parent, "settings"):
                s = getattr(parent.settings, "resource_graph_monitor_gpu_index", None)
                if isinstance(s, int) and s >= 0:
                    want = s
        except Exception:
            want = 0
        for i in range(self._gpu_monitor_combo.count()):
            if int(self._gpu_monitor_combo.itemData(i)) == want:
                self._gpu_monitor_combo.setCurrentIndex(i)
                self._monitor_gpu_index = want
                break
        else:
            self._monitor_gpu_index = int(self._gpu_monitor_combo.currentData() or 0)
        self._gpu_monitor_combo.blockSignals(False)

    def _on_purge_clicked(self) -> None:
        self._purge_btn.setEnabled(False)
        self._purge_status_lbl.setText("Purging…")
        self._purge_status_lbl.setStyleSheet("color: #FFB703; font-size: 11px;")
        try:
            try:
                from src.util.utils_vram import purge_process_memory_aggressive

                purge_process_memory_aggressive()
            except Exception as e:
                self._purge_status_lbl.setStyleSheet("color: #FE2C55; font-size: 11px;")
                self._purge_status_lbl.setText(str(e)[:200])
                self._purge_btn.setEnabled(True)
                return
            self._purge_status_lbl.setStyleSheet("color: #25F4EE; font-size: 11px;")
            self._purge_status_lbl.setText("Purged Python GC + GPU cache (see tooltip for limits).")
            par = self.parent()
            if par is not None and hasattr(par, "_append_log"):
                try:
                    par._append_log("Resource monitor: Purge memory (GC + CUDA cache on all devices).")
                except Exception:
                    pass
            QTimer.singleShot(3200, self._clear_purge_status)
        finally:
            self._purge_btn.setEnabled(True)

    def _clear_purge_status(self) -> None:
        try:
            self._purge_status_lbl.setText("")
            self._purge_status_lbl.setStyleSheet("color: #8A96A3; font-size: 11px;")
        except Exception:
            pass

    def _on_monitor_gpu_changed(self, _idx: int) -> None:
        raw = self._gpu_monitor_combo.currentData()
        self._monitor_gpu_index = int(raw) if raw is not None else 0
        self._gpu_chart.clear_data()
        parent = self.parent()
        if parent is not None and hasattr(parent, "settings") and hasattr(parent, "_save_settings"):
            try:
                from dataclasses import replace

                from src.core.config import AppSettings

                cur = parent.settings
                if isinstance(cur, AppSettings):
                    parent.settings = replace(cur, resource_graph_monitor_gpu_index=self._monitor_gpu_index)
                    parent._save_settings()
            except Exception:
                pass

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        parent = self.parent()
        self._split_chk.blockSignals(True)
        try:
            if parent is not None and hasattr(parent, "settings"):
                self._split_chk.setChecked(bool(getattr(parent.settings, "resource_graph_split_view", False)))
        except Exception:
            self._split_chk.setChecked(False)
        self._split_chk.blockSignals(False)

        self._populate_monitor_combo()
        self._apply_gpu_view_mode()
        try:
            import os

            import psutil

            psutil.Process(os.getpid()).cpu_percent(None)
        except Exception:
            pass
        self._timer.start()

    def hideEvent(self, event) -> None:  # type: ignore[override]
        self._timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._timer.stop()
        super().closeEvent(event)

    def _on_tick(self) -> None:
        try:
            s = sample_aquaduct_resources()
            self._cpu_chart.push(s.process_cpu_pct)
            self._ram_chart.push(s.process_ram_pct)
            self._cpu_lbl.setText(f"CPU {s.process_cpu_pct:5.1f}%")
            self._cpu_lbl.setToolTip(
                "Process-tree CPU (Python + subprocesses). Spikes during encode often include "
                "FFmpeg child processes (mux/micro-clips). "
                f"Child processes (recursive): {s.tree_child_count}."
            )
            ram_bits = [
                f"Aquaduct tree {s.process_ram_pct:5.1f}% of RAM",
                f"~{s.tree_rss_mb:.0f} MB RSS",
            ]
            if s.system_memory_used_pct is not None:
                ram_bits.append(f"system used {s.system_memory_used_pct:.0f}%")
            if s.available_ram_mb is not None:
                ram_bits.append(f"free ~{s.available_ram_mb:.0f} MB")
            self._ram_lbl.setText("RAM · " + " · ".join(ram_bits))
            self._ram_lbl.setToolTip(
                "Yellow sparkline: Aquaduct process tree RSS as % of total physical RAM (not the same as "
                "whole-machine usage). RSS MB sums resident pages for this process and children "
                "(e.g. FFmpeg). System used % is host-wide from psutil."
            )

            if self._split_chk.isChecked():
                for ix, title, lbl, chart in self._gpu_split_track:
                    pct = sample_gpu_mem_pct(ix)
                    if pct is not None:
                        chart.push(pct)
                        lbl.setText(f"{title} — VRAM {pct:5.1f}%")
                    else:
                        lbl.setText(f"{title} — VRAM —")
            else:
                gpu_pct = sample_gpu_mem_pct(self._monitor_gpu_index)
                if gpu_pct is not None:
                    self._gpu_chart.push(gpu_pct)
                    self._gpu_lbl.setText(f"GPU {self._monitor_gpu_index} VRAM {gpu_pct:5.1f}%")
                else:
                    self._gpu_lbl.setText("GPU VRAM —")
        except Exception:
            # Avoid crashing the main window if psutil/Qt/torch sampling misbehaves on a tick.
            pass
