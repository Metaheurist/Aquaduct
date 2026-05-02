"""Modal-less frameless window: CPU/RAM/GPU usage — compact text summary or expanded live charts."""

from __future__ import annotations

import math
from collections import deque

from PyQt6.QtCore import QPointF, QTimer, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from UI.dialogs.frameless_dialog import FramelessDialog
from UI.help.tutorial_links import help_tooltip_rich
from UI.widgets.no_wheel_controls import NoWheelComboBox
from UI.widgets.title_bar_outline_button import styled_outline_button

from src.models.hardware import list_cuda_gpus
from src.util.resource_sample import ResourceSample, sample_aquaduct_resources, sample_gpu_mem_pct, vram_sparkline_y_axis_cap

_HISTORY = 120  # 2 minutes at 1 Hz

_SPLIT_GPU_COLORS = ("#A78BFA", "#F472B6", "#34D399", "#FB923C", "#38BDF8", "#E879F9")
# ``QComboBox`` userData for the synthetic “Split view” row (not a CUDA ordinal).
_MONITOR_COMBO_SPLIT_SENTINEL = -1
# Metrics row: at most this many columns (CPU / RAM / single GPU).
_RESOURCE_GRAPH_GRID_MAX_COLS = 3

# Minimal/summary layout: narrow windows crush the Monitor combo + purge/expand/close row.
_RESOURCE_GRAPH_COMPACT_MIN_WIDTH = 660
_RESOURCE_GRAPH_COMPACT_COMBO_MIN = 248
_RESOURCE_GRAPH_COMPACT_COMBO_MAX = 400


class _SparklineChart(QWidget):
    """Simple 0–100 time series drawn as a polyline (expanded Resource usage only)."""

    def __init__(
        self,
        *,
        color: str,
        y_label: str = "0–100%",
        show_footer: bool = True,
        vram_auto_y: bool = False,
    ) -> None:
        super().__init__()
        self._data: deque[float] = deque(maxlen=_HISTORY)
        self._color = QColor(color)
        self._y_label = y_label
        self._show_footer = show_footer
        self._vram_auto_y = vram_auto_y
        self.setMinimumHeight(128)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_expanded_metrics(self, *, show_footer: bool | None = None, min_h: int | None = None) -> None:
        if show_footer is not None:
            self._show_footer = show_footer
        if min_h is not None:
            self.setMinimumHeight(max(72, min_h))
        else:
            self.setMinimumHeight(128)
        self.setMinimumWidth(300)
        self.update()

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
        pad_b = 8.0 if not self._show_footer else 22.0
        pad_l, pad_r, pad_t = 44.0, 8.0, 8.0
        inner_w = max(1.0, w - pad_l - pad_r)
        inner_h = max(1.0, h - pad_t - pad_b)

        plot_left = int(pad_l)
        plot_top = int(pad_t)
        plot_w = int(inner_w)
        plot_h = int(inner_h)
        plot_right = plot_left + plot_w
        plot_bottom = plot_top + plot_h

        # Plot frame
        painter.setPen(QPen(QColor("#3D3D4A"), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(plot_left, plot_top, plot_w, plot_h)

        # Minor horizontal (25%, 75%)
        minor_pen = QPen(QColor("#333340"), 1.0, Qt.PenStyle.DashLine)
        painter.setPen(minor_pen)
        for frac in (0.25, 0.75):
            y = int(pad_t + inner_h * frac)
            painter.drawLine(plot_left, y, plot_right, y)

        # Major horizontal (0%, 50%, 100%)
        painter.setPen(QPen(QColor("#4A4A5C"), 1.25))
        for frac in (0.0, 0.5, 1.0):
            y = int(pad_t + inner_h * frac)
            painter.drawLine(plot_left, y, plot_right, y)

        # Vertical grid (subtle time divisions)
        n_vert = 8
        painter.setPen(QPen(QColor("#2F2F3A"), 1.0))
        for i in range(1, n_vert):
            x = plot_left + (plot_w * i) // n_vert
            painter.drawLine(x, plot_top, x, plot_bottom)

        n = len(self._data)
        if n < 2:
            painter.setPen(QColor("#8A96A3"))
            painter.drawText(int(pad_l + 8), int(pad_t + inner_h // 2), "Collecting samples…")
            return

        y_cap = vram_sparkline_y_axis_cap(self._data) if self._vram_auto_y else 100.0
        y_cap = max(1.0, y_cap)

        painter.setPen(QColor("#6A7080"))
        painter.drawText(4, int(pad_t + 6), f"{y_cap:.0f}")
        painter.drawText(4, int(pad_t + inner_h // 2 + 4), f"{y_cap * 0.5:.0f}")
        painter.drawText(4, int(pad_t + inner_h - 2), "0")

        pts: list[tuple[float, float]] = []
        for i, v in enumerate(self._data):
            x = pad_l + inner_w * (i / max(1, n - 1))
            y = pad_t + inner_h * (1.0 - min(float(v), y_cap) / y_cap)
            pts.append((x, y))

        painter.setPen(QPen(self._color, 2.0))
        for i in range(1, len(pts)):
            painter.drawLine(int(pts[i - 1][0]), int(pts[i - 1][1]), int(pts[i][0]), int(pts[i][1]))

        # Fill under curve
        if len(pts) >= 2:
            poly = QPolygonF(
                [QPointF(pts[0][0], pad_t + inner_h)]
                + [QPointF(a, b) for a, b in pts]
                + [QPointF(pts[-1][0], pad_t + inner_h)]
            )
            c = QColor(self._color)
            c.setAlpha(45)
            painter.setBrush(QBrush(c))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(poly)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        if self._show_footer:
            painter.setPen(QColor("#B7B7C2"))
            foot = f"{self._y_label}  •  window: last {n}s"
            if self._vram_auto_y:
                foot += f"  •  Y-axis 0–{y_cap:.0f}% VRAM"
            painter.drawText(int(pad_l), int(h - 4), foot)


class _MiniCpuCoreSparkline(QWidget):
    """One logical CPU: system-wide utilization history in a compact cell (expanded CPU column)."""

    def __init__(self, *, color: str, core_index: int) -> None:
        super().__init__()
        self._color = QColor(color)
        self._core_index = core_index
        self._data: deque[float] = deque(maxlen=_HISTORY)
        self.setMinimumSize(28, 28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setToolTip(f"Logical CPU {core_index}")

    def history_len(self) -> int:
        return len(self._data)

    def push(self, value: float, *, tip_suffix: str | None = None) -> None:
        self._data.append(max(0.0, min(100.0, value)))
        last = float(self._data[-1])
        if tip_suffix:
            self.setToolTip(tip_suffix)
        else:
            self.setToolTip(f"Logical CPU {self._core_index}\nSystem-wide on this core: {last:.0f}%")
        self.update()

    def clear_data(self) -> None:
        self._data.clear()
        self.setToolTip(f"Logical CPU {self._core_index}")
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        pad_l, pad_r, pad_t, pad_b = 3.0, 3.0, 3.0, 3.0
        inner_w = max(1.0, w - pad_l - pad_r)
        inner_h = max(1.0, h - pad_t - pad_b)

        plot_left = int(pad_l)
        plot_top = int(pad_t)
        plot_w = int(inner_w)
        plot_h = int(inner_h)
        plot_right = plot_left + plot_w
        plot_bottom = plot_top + plot_h

        painter.setPen(QPen(QColor("#3D3D4A"), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(plot_left, plot_top, plot_w, plot_h)

        painter.setPen(QPen(QColor("#4A4A5C"), 1.0))
        for frac in (0.5,):
            y = int(pad_t + inner_h * frac)
            painter.drawLine(plot_left, y, plot_right, y)

        n = len(self._data)
        if n >= 2:
            pts: list[tuple[float, float]] = []
            y_cap = 100.0
            for i, v in enumerate(self._data):
                x = pad_l + inner_w * (i / max(1, n - 1))
                y = pad_t + inner_h * (1.0 - min(float(v), y_cap) / y_cap)
                pts.append((x, y))

            painter.setPen(QPen(self._color, 1.35))
            for i in range(1, len(pts)):
                painter.drawLine(int(pts[i - 1][0]), int(pts[i - 1][1]), int(pts[i][0]), int(pts[i][1]))

            if len(pts) >= 2:
                poly = QPolygonF(
                    [QPointF(pts[0][0], pad_t + inner_h)]
                    + [QPointF(a, b) for a, b in pts]
                    + [QPointF(pts[-1][0], pad_t + inner_h)]
                )
                c = QColor(self._color)
                c.setAlpha(40)
                painter.setBrush(QBrush(c))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPolygon(poly)
        else:
            painter.setPen(QColor("#8A96A3"))
            painter.drawText(
                self.rect().adjusted(2, 2, -2, -2),
                int(Qt.AlignmentFlag.AlignCenter),
                "…",
            )

        painter.setPen(QColor("#7C8494"))
        painter.setFont(self.font())
        f = painter.font()
        f.setPointSize(max(6, f.pointSize() - 2))
        painter.setFont(f)
        painter.drawText(plot_left + 2, plot_bottom - 2, str(self._core_index))


class _CpuPerCoreChartArea(QWidget):
    """Fills the CPU chart cell with a roughly square grid of per-core host CPU mini sparklines."""

    def __init__(self, *, accent: str = "#25F4EE") -> None:
        super().__init__()
        self._accent = accent
        self._tiles: list[_MiniCpuCoreSparkline] = []
        self._n = 0
        self._show_footer = True
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)
        lay.addWidget(self._grid_host, 1)
        self._footer = QLabel("")
        self._footer.setWordWrap(True)
        self._footer.setStyleSheet("color: #B7B7C2; font-size: 11px;")
        lay.addWidget(self._footer)
        self.setMinimumHeight(128)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_expanded_metrics(self, *, show_footer: bool | None = None, min_h: int | None = None) -> None:
        if show_footer is not None:
            self._show_footer = show_footer
            self._footer.setVisible(show_footer)
        mh = 128 if min_h is None else max(72, min_h)
        self.setMinimumHeight(mh)
        self.setMinimumWidth(300)

    def clear_data(self) -> None:
        for t in self._tiles:
            t.clear_data()

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._tiles.clear()
        self._n = 0

    def rebuild_if_needed(self, n_cores: int) -> None:
        n = max(1, int(n_cores))
        if n == self._n and len(self._tiles) == n:
            return
        self._clear_grid()
        self._n = n
        cols = max(1, int(math.ceil(n**0.5)))
        rows = (n + cols - 1) // cols
        for i in range(n):
            tile = _MiniCpuCoreSparkline(color=self._accent, core_index=i)
            r, c = divmod(i, cols)
            self._grid.addWidget(tile, r, c)
            self._tiles.append(tile)
        for r in range(rows):
            self._grid.setRowStretch(r, 1)
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)

    def push_sample(self, s: ResourceSample) -> None:
        per = s.host_cpu_per_core_pct
        if len(per) >= 1:
            self.rebuild_if_needed(len(per))
            for i, v in enumerate(per):
                self._tiles[i].push(v)
            span = self._tiles[0].history_len() if self._tiles else 0
            if self._show_footer:
                self._footer.setText(
                    "Host per-logical-CPU % (system-wide); grid is row-major (0 top-left). • "
                    f"window: last {span}s  •  Aquaduct process tree (÷ cores): {s.process_cpu_pct:.1f}%"
                )
        else:
            self.rebuild_if_needed(1)
            self._tiles[0].push(
                s.process_cpu_pct,
                tip_suffix=(
                    "Aquaduct process tree (Python + children), as % of one full logical CPU.\n"
                    f"Current: {s.process_cpu_pct:.1f}% — per-core host graph unavailable on this tick."
                ),
            )
            span = self._tiles[0].history_len()
            if self._show_footer:
                self._footer.setText(
                    f"Process-tree CPU % (÷ logical cores); per-core host sampling unavailable. • window: last {span}s"
                )


class ResourceGraphDialog(FramelessDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Resource usage")
        self.setModal(False)
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._monitor_gpu_index = 0
        self._gpu_split_track: list[tuple[int, str, QLabel, _SparklineChart]] = []
        self._compact_mode = self._compact_mode_from_parent()

        self._cpu_lbl = QLabel("CPU — —%")
        self._cpu_lbl.setStyleSheet("color: #25F4EE; font-weight: 700; font-size: 12px;")
        self._cpu_chart = _CpuPerCoreChartArea(accent="#25F4EE")
        self._ram_lbl = QLabel("RAM — —%")
        self._ram_lbl.setStyleSheet("color: #FFB703; font-weight: 700; font-size: 12px;")
        self._ram_chart = _SparklineChart(
            color="#FFB703",
            y_label="RAM % of system",
            show_footer=True,
        )
        self._gpu_lbl = QLabel("GPU VRAM —")
        self._gpu_lbl.setStyleSheet("color: #A78BFA; font-weight: 700; font-size: 12px;")
        self._gpu_chart = _SparklineChart(
            color="#A78BFA",
            y_label="VRAM % (CUDA)",
            show_footer=True,
            vram_auto_y=True,
        )

        self._metrics_host = QWidget()
        self._metrics_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._metrics_grid = QGridLayout(self._metrics_host)
        self._metrics_grid.setContentsMargins(0, 0, 0, 0)
        self._metrics_grid.setHorizontalSpacing(10)
        self._metrics_grid.setVerticalSpacing(8)
        self._metrics_grid.setRowStretch(0, 1)
        self._sync_metrics_grid_stretches(False)

        self._cpu_cell = QWidget()
        cpu_lay = QVBoxLayout(self._cpu_cell)
        self._cpu_cell_lay = cpu_lay
        cpu_lay.setContentsMargins(0, 0, 0, 0)
        cpu_lay.setSpacing(4)
        cpu_lay.addWidget(self._cpu_lbl)
        cpu_lay.addWidget(self._cpu_chart, 1)
        self._cpu_cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        ram_cell = QWidget()
        ram_lay = QVBoxLayout(ram_cell)
        self._ram_cell_lay = ram_lay
        ram_lay.setContentsMargins(0, 0, 0, 0)
        ram_lay.setSpacing(4)
        ram_lay.addWidget(self._ram_lbl)
        ram_lay.addWidget(self._ram_chart, 1)
        ram_cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._gpu_single_cell = QWidget()
        gpu_single_lay = QVBoxLayout(self._gpu_single_cell)
        self._gpu_single_cell_lay = gpu_single_lay
        gpu_single_lay.setContentsMargins(0, 0, 0, 0)
        gpu_single_lay.setSpacing(4)
        gpu_single_lay.addWidget(self._gpu_lbl)
        gpu_single_lay.addWidget(self._gpu_chart, 1)
        self._gpu_single_cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._metrics_grid.addWidget(self._cpu_cell, 0, 0)
        self._metrics_grid.addWidget(ram_cell, 0, 1)
        self._metrics_grid.addWidget(self._gpu_single_cell, 0, 2)

        self._compact_list_host = QWidget()
        self._compact_list_host.setVisible(False)
        self._compact_list_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._compact_vbox = QVBoxLayout(self._compact_list_host)
        self._compact_vbox.setContentsMargins(0, 0, 0, 0)
        self._compact_vbox.setSpacing(6)

        self.body_layout.addWidget(self._compact_list_host)
        self.body_layout.addWidget(self._metrics_host, 1)

        branding = None
        try:
            par = parent
            if par is not None and hasattr(par, "settings"):
                branding = getattr(par.settings, "branding", None)
        except Exception:
            branding = None
        self._purge_btn = styled_outline_button(
            "",
            "accent_icon",
            icon_kind="purge",
            fixed=(40, 32),
            branding=branding,
        )
        self._purge_btn.setAccessibleName("Purge memory")
        self._purge_btn.setToolTip(
            help_tooltip_rich(
                "Purge memory — runs aggressive Python garbage collection and clears the PyTorch CUDA cache "
                "for this Aquaduct process on all GPUs (and MPS cache on Apple Silicon). Frees unreachable objects "
                "and returns caching-allocator memory to the driver.\n\n"
                "VRAM % in these charts is whole-GPU utilization (desktop compositor, other apps, leftover driver "
                "pools)—not Aquaduct alone—so percentages often stay above zero after purge. Purge cannot unload "
                "models still referenced or free memory owned by other programs. It does not force-unload weights "
                "held by a running pipeline job.",
                "welcome",
                slide=2,
            )
        )
        self._purge_btn.clicked.connect(self._on_purge_clicked)
        self._monitor_lbl = QLabel("Monitor:")
        self._monitor_lbl.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 600;")
        self._monitor_lbl.setToolTip(
            help_tooltip_rich(
                "Which CUDA GPU to plot VRAM for in the single-GPU chart (ignored when Split view — all GPUs "
                "is selected). Pipeline device policy is configured on Model → My PC; this dropdown only picks "
                "what the monitor graphs.",
                "welcome",
                slide=2,
            )
        )
        self._gpu_monitor_combo = NoWheelComboBox()
        self._gpu_monitor_combo.setMinimumWidth(180)
        self._gpu_monitor_combo.setMaximumWidth(320)
        self._gpu_monitor_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._gpu_monitor_combo.setToolTip(
            help_tooltip_rich(
                "Pick one CUDA device to chart VRAM %, or choose “Split view — all GPUs” for a separate "
                "sparkline per GPU (scroll when many devices). In Auto GPU policy, script (LLM) and "
                "diffusion may use different cards — switch devices to compare. ~70–90% on the active GPU "
                "during a run is normal.",
                "welcome",
                slide=2,
            )
        )
        self._gpu_monitor_combo.view().setMouseTracking(True)
        self._layout_toggle_btn = styled_outline_button(
            "",
            "muted_icon",
            icon_kind="resource_expand" if self._compact_mode else "resource_compress",
            fixed=(40, 32),
            branding=branding,
        )
        self._layout_toggle_btn.setAccessibleName("Toggle usage summary vs live charts")
        self._layout_toggle_btn.clicked.connect(self._on_layout_toggle_clicked)
        self._sync_layout_toggle_button()

        self._title_monitor_tools = QWidget()
        _tm = QHBoxLayout(self._title_monitor_tools)
        _tm.setContentsMargins(0, 0, 0, 0)
        _tm.setSpacing(8)
        _tm.addWidget(self._monitor_lbl, 0)
        _tm.addWidget(self._gpu_monitor_combo, 0)

        # Purge + expand + close as one tight group (Monitor dropdown sits left of this cluster).
        close_btn = self._frameless_close_button
        self._title_bar_layout.removeWidget(close_btn)
        self._title_icon_cluster = QWidget()
        _ic = QHBoxLayout(self._title_icon_cluster)
        _ic.setContentsMargins(0, 0, 0, 0)
        _ic.setSpacing(4)
        _ic.addWidget(self._purge_btn, 0)
        _ic.addWidget(self._layout_toggle_btn, 0)
        _ic.addWidget(close_btn, 0)
        self._title_bar_layout.addWidget(self._title_monitor_tools, 0)
        self._title_bar_layout.addWidget(self._title_icon_cluster, 0)
        self._title_bar_layout.setSpacing(10)

        self._sync_compact_title_bar_widths()

        self._gpu_split_inner = QWidget()
        self._gpu_split_inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self._gpu_split_rows_layout = QVBoxLayout(self._gpu_split_inner)
        self._gpu_split_rows_layout.setContentsMargins(0, 4, 0, 0)
        self._gpu_split_rows_layout.setSpacing(10)
        self._gpu_split_scroll = QScrollArea()
        self._gpu_split_scroll.setWidgetResizable(True)
        self._gpu_split_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._gpu_split_scroll.setWidget(self._gpu_split_inner)
        self._gpu_split_scroll.setMinimumHeight(140)
        self._gpu_split_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._gpu_split_scroll.setVisible(False)
        self.body_layout.addWidget(self._gpu_split_scroll, 1)

        self._purge_status_lbl = QLabel("")
        self._purge_status_lbl.setStyleSheet("color: #8A96A3; font-size: 11px;")
        self._purge_status_lbl.setWordWrap(True)
        self.body_layout.addWidget(self._purge_status_lbl)
        self._sync_purge_status_visibility()

        self._gpu_monitor_combo.currentIndexChanged.connect(self._on_monitor_gpu_changed)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        self._apply_compact_charts_visibility()
        self._sync_compact_chart_shell()

    def _sync_compact_title_bar_widths(self) -> None:
        """Compact mode needs a wider floor so title + Monitor + combo + icons do not overlap."""
        compact = getattr(self, "_compact_mode", True)
        if compact:
            self._gpu_monitor_combo.setMinimumWidth(_RESOURCE_GRAPH_COMPACT_COMBO_MIN)
            self._gpu_monitor_combo.setMaximumWidth(_RESOURCE_GRAPH_COMPACT_COMBO_MAX)
            self._title_lbl.setMinimumWidth(118)
        else:
            self._gpu_monitor_combo.setMinimumWidth(180)
            self._gpu_monitor_combo.setMaximumWidth(320)
            self._title_lbl.setMinimumWidth(0)

    def _compact_mode_from_parent(self) -> bool:
        try:
            p = self.parent()
            if p is not None and hasattr(p, "settings"):
                return bool(getattr(p.settings, "resource_graph_compact", True))
        except Exception:
            pass
        return True

    def _clear_compact_list_layout_keep_widgets(self) -> None:
        while self._compact_vbox.count():
            it = self._compact_vbox.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)

    def _restore_chart_grid_labels(self) -> None:
        """Put CPU/RAM/GPU labels back into the chart grid after minimal list mode."""
        split = self._monitor_combo_is_split_view()
        while self._compact_vbox.count():
            it = self._compact_vbox.takeAt(0)
            w = it.widget()
            if w is None:
                continue
            w.setParent(None)
            if w not in (self._cpu_lbl, self._ram_lbl, self._gpu_lbl):
                w.deleteLater()
        self._cpu_cell_lay.insertWidget(0, self._cpu_lbl)
        self._ram_cell_lay.insertWidget(0, self._ram_lbl)
        self._gpu_single_cell_lay.insertWidget(0, self._gpu_lbl)
        self._cpu_lbl.setWordWrap(False)
        self._ram_lbl.setWordWrap(False)
        self._gpu_lbl.setWordWrap(False)

    def _reparent_labels_into_compact_list(self) -> None:
        """Minimal mode: vertical list — CPU, RAM, then each GPU line."""
        self._clear_compact_list_layout_keep_widgets()
        self._cpu_cell_lay.removeWidget(self._cpu_lbl)
        self._ram_cell_lay.removeWidget(self._ram_lbl)
        self._cpu_lbl.setWordWrap(True)
        self._ram_lbl.setWordWrap(True)
        self._compact_vbox.addWidget(self._cpu_lbl)
        self._compact_vbox.addWidget(self._ram_lbl)
        if self._monitor_combo_is_split_view():
            for _ix, _title, lbl, _chart in self._gpu_split_track:
                vl = lbl.parentWidget().layout() if lbl.parentWidget() else None
                if vl is not None:
                    vl.removeWidget(lbl)
                lbl.setWordWrap(True)
                self._compact_vbox.addWidget(lbl)
        else:
            self._gpu_single_cell_lay.removeWidget(self._gpu_lbl)
            self._gpu_lbl.setWordWrap(True)
            self._compact_vbox.addWidget(self._gpu_lbl)

    def _sync_compact_chart_shell(self) -> None:
        """Toggle minimal list vs chart grid + split panel; refresh GPU rows when needed."""
        split = self._monitor_combo_is_split_view()
        if self._compact_mode:
            self._metrics_host.setVisible(False)
            self._gpu_split_scroll.setVisible(False)
            self._sync_metrics_grid_stretches(split)
            if split:
                self._rebuild_split_gpu_ui()
            else:
                self._clear_split_gpu_panel()
            self._reparent_labels_into_compact_list()
            self._compact_list_host.setVisible(True)
        else:
            self._compact_list_host.setVisible(False)
            self._restore_chart_grid_labels()
            self._metrics_host.setVisible(True)
            self._gpu_single_cell.setVisible(not split)
            self._gpu_split_scroll.setVisible(split)
            self._sync_metrics_grid_stretches(split)
            if split:
                self._rebuild_split_gpu_ui()
            else:
                self._clear_split_gpu_panel()
        self._adjust_resource_window_geometry()
        self._sync_resource_body_layout()

    def _sync_metrics_grid_stretches(self, split: bool) -> None:
        """When split view hides the single-GPU column, drop stretch on the empty third column."""
        nc = _RESOURCE_GRAPH_GRID_MAX_COLS
        if split:
            self._metrics_grid.setColumnStretch(0, 1)
            self._metrics_grid.setColumnStretch(1, 1)
            if nc > 2:
                self._metrics_grid.setColumnStretch(2, 0)
        else:
            for c in range(nc):
                self._metrics_grid.setColumnStretch(c, 1)

    def _apply_compact_charts_visibility(self) -> None:
        show_charts = not self._compact_mode
        self._cpu_chart.setVisible(show_charts)
        self._ram_chart.setVisible(show_charts)
        self._gpu_chart.setVisible(show_charts)
        for _ix, _title, _lbl, chart in self._gpu_split_track:
            chart.setVisible(show_charts)
        if not show_charts:
            # Hidden charts still reported ~128px min height to layouts unless cleared (summary mode gap).
            for ch in (self._cpu_chart, self._ram_chart, self._gpu_chart):
                ch.setMinimumHeight(0)
            for _ix, _title, _lbl, chart in self._gpu_split_track:
                chart.setMinimumHeight(0)

    def _sync_resource_body_layout(self) -> None:
        """Summary mode: vertical list, no wasted stretch. Chart mode: grid + charts fill."""
        compact = self._compact_mode
        try:
            split = self._monitor_combo_is_split_view()
        except Exception:
            split = False

        self._metrics_grid.setRowStretch(0, 0 if compact else 1)
        if compact:
            self._metrics_host.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            self._compact_list_host.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        else:
            self._metrics_host.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self._compact_list_host.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # body_layout: 0 compact list, 1 metrics grid, 2 split scroll, 3 purge status
        if compact:
            self.body_layout.setStretch(0, 0)
            self.body_layout.setStretch(1, 0)
            self.body_layout.setStretch(2, 0)
            self.body_layout.setStretch(3, 0)
        else:
            m_stretch, g_stretch = (1, 1 if split else 0)
            self.body_layout.setStretch(0, 0)
            self.body_layout.setStretch(1, m_stretch)
            self.body_layout.setStretch(2, g_stretch)
            self.body_layout.setStretch(3, 0)
        self.body_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def _on_layout_toggle_clicked(self) -> None:
        self._set_resource_view_compact(not self._compact_mode, persist=True)

    def _sync_layout_toggle_button(self) -> None:
        if self._compact_mode:
            self._layout_toggle_btn.set_icon_kind("resource_expand")
            self._layout_toggle_btn.setToolTip(
                help_tooltip_rich(
                    "Expand to live charts: sparklines with grid axes, footers, and taller layout for split "
                    "GPU rows. Your choice is remembered.",
                    "welcome",
                    slide=2,
                )
            )
        else:
            self._layout_toggle_btn.set_icon_kind("resource_compress")
            self._layout_toggle_btn.setToolTip(
                help_tooltip_rich(
                    "Summary mode (default): numbers only — no charts — compact window. Purge status stays "
                    "hidden until you purge or expand. Your choice is remembered.",
                    "welcome",
                    slide=2,
                )
            )

    def _sync_purge_status_visibility(self) -> None:
        txt = (self._purge_status_lbl.text() or "").strip()
        self._purge_status_lbl.setVisible(not self._compact_mode or bool(txt))

    def _set_resource_view_compact(self, compact: bool, *, persist: bool = True) -> None:
        prev = self._compact_mode
        self._compact_mode = compact
        if prev != compact:
            if not compact:
                for ch in (self._cpu_chart, self._ram_chart, self._gpu_chart):
                    ch.set_expanded_metrics(show_footer=True, min_h=128)
            else:
                for ch in (self._cpu_chart, self._ram_chart, self._gpu_chart):
                    ch.set_expanded_metrics(show_footer=False, min_h=128)
        self._apply_compact_charts_visibility()
        self._sync_purge_status_visibility()
        self._sync_layout_toggle_button()
        self._sync_compact_chart_shell()
        if persist:
            par = self.parent()
            if par is not None and hasattr(par, "settings") and hasattr(par, "_save_settings"):
                try:
                    from dataclasses import replace

                    from src.core.config import AppSettings

                    cur = par.settings
                    if isinstance(cur, AppSettings):
                        par.settings = replace(cur, resource_graph_compact=compact)
                        par._save_settings()
                except Exception:
                    pass

    def _adjust_resource_window_geometry(self) -> None:
        """Minimum window size from metrics mode, split GPU rows, and chart vs summary layout."""
        gpus = list_cuda_gpus()
        n_gpu = max(1, len(gpus))
        nc = _RESOURCE_GRAPH_GRID_MAX_COLS
        split_rows = (n_gpu + nc - 1) // nc
        compact = getattr(self, "_compact_mode", True)
        try:
            split_visible = self._monitor_combo_is_split_view()
        except Exception:
            split_visible = False
        if compact:
            split_row = 30
            split_cap = 120 + split_rows * split_row
            col_w = 120
            min_w_floor = _RESOURCE_GRAPH_COMPACT_MIN_WIDTH
            n_lines = 2 + (n_gpu if split_visible else 1)
            base_h = 44 + n_lines * 26
            req_w = min_w_floor
        else:
            split_row = 118
            split_cap = 560
            col_w = 200
            base_h = 460
            min_w_floor = 500
            min_w = 72 + nc * col_w
            req_w = max(min_w_floor, min_w)
        split_h = min(split_cap, max(80, split_rows * split_row + (24 if compact else 36)))
        if split_visible and not compact:
            self._gpu_split_scroll.setMinimumHeight(split_h)
        else:
            self._gpu_split_scroll.setMinimumHeight(0)
        if compact:
            req_h = base_h
        else:
            req_h = base_h + (split_h if split_visible else 0)
        self._sync_compact_title_bar_widths()
        self.setMinimumWidth(req_w)
        self.setMinimumHeight(req_h)
        # Enlarge the window when minimums increase (e.g. compact↔expanded toggle) so content is not clipped.
        gw, gh = self.width(), self.height()
        if gw < req_w or gh < req_h:
            self.resize(max(gw, req_w), max(gh, req_h))
        elif compact:
            nw = req_w if gw > req_w else gw
            nh = req_h if gh > req_h else gh
            if nw != gw or nh != gh:
                self.resize(int(nw), int(nh))

    def _clear_split_gpu_panel(self) -> None:
        self._gpu_split_track.clear()
        while self._gpu_split_rows_layout.count():
            item = self._gpu_split_rows_layout.takeAt(0)
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

        nc = _RESOURCE_GRAPH_GRID_MAX_COLS
        compact = self._compact_mode
        for row_start in range(0, len(specs), nc):
            chunk = specs[row_start : row_start + nc]
            row_w = QWidget()
            row_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            hl = QHBoxLayout(row_w)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(8)
            for i, (ix, title) in enumerate(chunk):
                global_i = row_start + i
                color = _SPLIT_GPU_COLORS[global_i % len(_SPLIT_GPU_COLORS)]
                lbl = QLabel(f"{title} — VRAM …")
                lbl.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 11px;")
                lbl.setToolTip(
                    help_tooltip_rich(
                        f"VRAM % for {title}. In expanded mode a sparkline is shown; summary mode is text only.",
                        "welcome",
                        slide=2,
                    )
                )
                chart = _SparklineChart(
                    color=color,
                    y_label=f"GPU {ix} VRAM %",
                    show_footer=not compact,
                    vram_auto_y=True,
                )
                if compact:
                    chart.set_expanded_metrics(show_footer=False, min_h=72)
                else:
                    chart.set_expanded_metrics(show_footer=True, min_h=100)
                cell = QWidget()
                cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                vl = QVBoxLayout(cell)
                vl.setContentsMargins(0, 0, 0, 0)
                vl.setSpacing(4)
                vl.addWidget(lbl)
                vl.addWidget(chart, 1)
                hl.addWidget(cell, 1)
                self._gpu_split_track.append((ix, title, lbl, chart))
            self._gpu_split_rows_layout.addWidget(row_w)
        self._apply_compact_charts_visibility()

    def _monitor_combo_is_split_view(self) -> bool:
        d = self._gpu_monitor_combo.currentData()
        try:
            return int(d) == _MONITOR_COMBO_SPLIT_SENTINEL
        except (TypeError, ValueError):
            return False

    def _apply_gpu_view_mode(self) -> None:
        self._sync_compact_chart_shell()

    def _populate_monitor_combo(self) -> None:
        self._gpu_monitor_combo.blockSignals(True)
        self._gpu_monitor_combo.clear()
        gpus = list_cuda_gpus()
        tip_role = Qt.ItemDataRole.ToolTipRole

        def _gpu_choice_tip(index: int, label: str) -> str:
            return help_tooltip_rich(
                f"Chart VRAM % for CUDA device {index}: {label}.\n\n"
                "Hover other rows to compare. Choose Split view — all GPUs for one sparkline per card.",
                "welcome",
                slide=2,
            )

        if not gpus:
            self._gpu_monitor_combo.addItem("GPU 0", 0)
            self._gpu_monitor_combo.setItemData(0, _gpu_choice_tip(0, "GPU 0"), tip_role)
        else:
            for g in gpus:
                row_ix = self._gpu_monitor_combo.count()
                disp = f"{g.index}: {g.name}"
                self._gpu_monitor_combo.addItem(disp, int(g.index))
                self._gpu_monitor_combo.setItemData(row_ix, _gpu_choice_tip(g.index, g.name), tip_role)

        split_ix = self._gpu_monitor_combo.count()
        self._gpu_monitor_combo.addItem("Split view — all GPUs", _MONITOR_COMBO_SPLIT_SENTINEL)
        self._gpu_monitor_combo.setItemData(
            split_ix,
            help_tooltip_rich(
                "One VRAM sparkline per CUDA GPU in a scrollable area — best when LLM and diffusion sit on "
                "different cards. The single-GPU column is hidden in this mode.",
                "welcome",
                slide=2,
            ),
            tip_role,
        )

        parent = self.parent()
        want_gpu = 0
        want_split = False
        try:
            if parent is not None and hasattr(parent, "settings"):
                want_split = bool(getattr(parent.settings, "resource_graph_split_view", False))
                s = getattr(parent.settings, "resource_graph_monitor_gpu_index", None)
                if isinstance(s, int) and s >= 0:
                    want_gpu = s
        except Exception:
            want_gpu = 0
            want_split = False

        self._monitor_gpu_index = want_gpu
        target_idx = -1
        if want_split:
            target_idx = self._gpu_monitor_combo.findData(_MONITOR_COMBO_SPLIT_SENTINEL, Qt.ItemDataRole.UserRole)
        if target_idx < 0:
            for i in range(self._gpu_monitor_combo.count()):
                d = self._gpu_monitor_combo.itemData(i)
                try:
                    di = int(d)
                except (TypeError, ValueError):
                    continue
                if di == _MONITOR_COMBO_SPLIT_SENTINEL:
                    continue
                if di == want_gpu:
                    target_idx = i
                    break
        if target_idx < 0:
            for i in range(self._gpu_monitor_combo.count()):
                try:
                    if int(self._gpu_monitor_combo.itemData(i)) != _MONITOR_COMBO_SPLIT_SENTINEL:
                        target_idx = i
                        break
                except (TypeError, ValueError):
                    continue
        if target_idx >= 0:
            self._gpu_monitor_combo.setCurrentIndex(target_idx)
            d_sel = self._gpu_monitor_combo.itemData(target_idx)
            try:
                if int(d_sel) != _MONITOR_COMBO_SPLIT_SENTINEL:
                    self._monitor_gpu_index = int(d_sel)
            except (TypeError, ValueError):
                pass

        self._gpu_monitor_combo.blockSignals(False)

    def _on_purge_clicked(self) -> None:
        self._purge_btn.setEnabled(False)
        self._purge_status_lbl.setVisible(True)
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
            self._sync_purge_status_visibility()
        except Exception:
            pass

    def _on_monitor_gpu_changed(self, _idx: int) -> None:
        raw = self._gpu_monitor_combo.currentData()
        parent = self.parent()

        try:
            is_split = int(raw) == _MONITOR_COMBO_SPLIT_SENTINEL
        except (TypeError, ValueError):
            is_split = False

        if is_split:
            self._gpu_chart.clear_data()
            self._apply_gpu_view_mode()
            if parent is not None and hasattr(parent, "settings") and hasattr(parent, "_save_settings"):
                try:
                    from dataclasses import replace

                    from src.core.config import AppSettings

                    cur = parent.settings
                    if isinstance(cur, AppSettings):
                        parent.settings = replace(cur, resource_graph_split_view=True)
                        parent._save_settings()
                except Exception:
                    pass
            return

        self._monitor_gpu_index = int(raw) if raw is not None else 0
        self._gpu_chart.clear_data()
        self._apply_gpu_view_mode()
        if parent is not None and hasattr(parent, "settings") and hasattr(parent, "_save_settings"):
            try:
                from dataclasses import replace

                from src.core.config import AppSettings

                cur = parent.settings
                if isinstance(cur, AppSettings):
                    parent.settings = replace(
                        cur,
                        resource_graph_monitor_gpu_index=self._monitor_gpu_index,
                        resource_graph_split_view=False,
                    )
                    parent._save_settings()
            except Exception:
                pass

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._populate_monitor_combo()
        self._apply_compact_charts_visibility()
        self._sync_compact_chart_shell()
        try:
            par = self.parent()
            if par is not None and hasattr(par, "settings"):
                want = bool(getattr(par.settings, "resource_graph_compact", True))
                if want != self._compact_mode:
                    self._set_resource_view_compact(want, persist=False)
        except Exception:
            pass
        try:
            import os

            import psutil

            psutil.Process(os.getpid()).cpu_percent(None)
            psutil.cpu_percent(percpu=True, interval=None)
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
            show_charts = not self._compact_mode
            if show_charts:
                self._cpu_chart.push_sample(s)
                self._ram_chart.push(s.process_ram_pct)
            self._cpu_lbl.setText(f"CPU {s.process_cpu_pct:5.1f}%")
            self._cpu_lbl.setToolTip(
                help_tooltip_rich(
                    "Headline: Aquaduct process-tree CPU as % of capacity (÷ logical cores).\n\n"
                    "Expanded chart: a grid of mini sparklines — each cell is system-wide utilization on one "
                    "logical CPU (not per-process allocation). FFmpeg and other children roll into the headline.\n\n"
                    f"Child processes (recursive): {s.tree_child_count}.",
                    "welcome",
                    slide=2,
                )
            )
            app_mb = s.tree_rss_mb
            used_mb = s.host_used_mb
            if used_mb is not None and used_mb >= 0.0:
                other_mb = max(0.0, used_mb - app_mb)
                self._ram_lbl.setText(
                    f"RAM · {app_mb:.0f} / {used_mb:.0f} MB — {app_mb:.0f} by app, {other_mb:.0f} by other"
                )
            else:
                self._ram_lbl.setText(f"RAM · {app_mb:.0f} MB by app")
            ram_body_parts = [
                (
                    "Yellow chart (expanded mode): Aquaduct process-tree RSS as % of total physical RAM."
                    if show_charts
                    else "Summary mode: values below are the same samples used for the RAM chart when expanded."
                ),
                f"Process tree RSS ≈ {app_mb:.0f} MB ({s.process_ram_pct:.1f}% of physical RAM).",
            ]
            if used_mb is not None:
                ram_body_parts.append(
                    f"Other ≈ psutil used RAM ({used_mb:.0f} MB) minus tree RSS — OS/file cache and "
                    "other apps; not exact accounting."
                )
            if s.system_memory_used_pct is not None:
                ram_body_parts.append(f"Host RAM reported in use: {s.system_memory_used_pct:.0f}%.")
            if s.available_ram_mb is not None:
                ram_body_parts.append(f"Available (reclaimable incl. cache): ~{s.available_ram_mb:.0f} MB.")
            self._ram_lbl.setToolTip(help_tooltip_rich("\n\n".join(ram_body_parts), "welcome", slide=2))

            if self._monitor_combo_is_split_view():
                for ix, title, lbl, chart in self._gpu_split_track:
                    pct = sample_gpu_mem_pct(ix)
                    if pct is not None:
                        if show_charts:
                            chart.push(pct)
                        lbl.setText(f"{title} — VRAM {pct:5.1f}%")
                    else:
                        lbl.setText(f"{title} — VRAM —")
            else:
                gpu_pct = sample_gpu_mem_pct(self._monitor_gpu_index)
                if gpu_pct is not None:
                    if show_charts:
                        self._gpu_chart.push(gpu_pct)
                    self._gpu_lbl.setText(f"GPU {self._monitor_gpu_index} VRAM {gpu_pct:5.1f}%")
                    self._gpu_lbl.setToolTip(
                        help_tooltip_rich(
                            f"VRAM % for CUDA device {self._monitor_gpu_index} (Monitor dropdown). "
                            f"Current sample: {gpu_pct:.1f}%.\n\n"
                            "Switch Monitor to compare cards; use Split view for all GPUs.",
                            "welcome",
                            slide=2,
                        )
                    )
                else:
                    self._gpu_lbl.setText("GPU VRAM —")
                    self._gpu_lbl.setToolTip(
                        help_tooltip_rich(
                            f"VRAM for CUDA device {self._monitor_gpu_index} — sample unavailable "
                            "(no CUDA or driver query failed).",
                            "welcome",
                            slide=2,
                        )
                    )
        except Exception:
            # Avoid crashing the main window if psutil/Qt/torch sampling misbehaves on a tick.
            pass
