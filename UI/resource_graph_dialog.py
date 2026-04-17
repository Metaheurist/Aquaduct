"""Modal-less frameless window: scrolling line charts for this process CPU/RAM and GPU VRAM."""

from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QPointF, QTimer, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from UI.frameless_dialog import FramelessDialog

from src.resource_sample import sample_aquaduct_resources

_HISTORY = 120  # 2 minutes at 1 Hz


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
        self.setMinimumHeight(460)

        hint = QLabel(
            "This Aquaduct process: CPU (share of one core), RAM (% of system memory), "
            "GPU VRAM (% of total) when CUDA is active. Updates every 1 second."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #B7B7C2; font-size: 11px;")
        self.body_layout.addWidget(hint)

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

        self._gpu_lbl = QLabel("GPU VRAM —")
        self._gpu_lbl.setStyleSheet("color: #A78BFA; font-weight: 700; font-size: 12px;")
        self.body_layout.addWidget(self._gpu_lbl)
        self._gpu_chart = _SparklineChart(color="#A78BFA", y_label="VRAM % (CUDA)")
        self.body_layout.addWidget(self._gpu_chart)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
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
        s = sample_aquaduct_resources()
        self._cpu_chart.push(s.process_cpu_pct)
        self._ram_chart.push(s.process_ram_pct)
        self._cpu_lbl.setText(f"CPU {s.process_cpu_pct:5.1f}% (process, vs one core = 100%)")
        self._ram_lbl.setText(f"RAM {s.process_ram_pct:5.1f}% of system (this process RSS)")

        if s.gpu_mem_pct is not None:
            self._gpu_chart.push(s.gpu_mem_pct)
            self._gpu_lbl.setText(f"GPU VRAM {s.gpu_mem_pct:5.1f}% of total (CUDA device)")
        else:
            self._gpu_lbl.setText("GPU VRAM n/a (CUDA not active or torch not on GPU)")
