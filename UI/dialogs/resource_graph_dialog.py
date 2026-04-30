"""Modal-less frameless window: CPU/RAM/GPU usage — compact text summary or expanded live charts."""

from __future__ import annotations

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
from src.util.resource_sample import sample_aquaduct_resources, sample_gpu_mem_pct

_HISTORY = 120  # 2 minutes at 1 Hz

_SPLIT_GPU_COLORS = ("#A78BFA", "#F472B6", "#34D399", "#FB923C", "#38BDF8", "#E879F9")
# ``QComboBox`` userData for the synthetic “Split view” row (not a CUDA ordinal).
_MONITOR_COMBO_SPLIT_SENTINEL = -1
# Metrics row: at most this many columns (CPU / RAM / single GPU).
_RESOURCE_GRAPH_GRID_MAX_COLS = 3


class _SparklineChart(QWidget):
    """Simple 0–100 time series drawn as a polyline (expanded Resource usage only)."""

    def __init__(self, *, color: str, y_label: str = "0–100%", show_footer: bool = True) -> None:
        super().__init__()
        self._data: deque[float] = deque(maxlen=_HISTORY)
        self._color = QColor(color)
        self._y_label = y_label
        self._show_footer = show_footer
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
            painter.drawText(int(pad_l), int(h - 4), f"{self._y_label}  •  window: last {n}s")


class ResourceGraphDialog(FramelessDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Resource usage")
        self.setModal(False)
        self._monitor_gpu_index = 0
        self._gpu_split_track: list[tuple[int, str, QLabel, _SparklineChart]] = []
        self._compact_mode = self._compact_mode_from_parent()

        self._cpu_lbl = QLabel("CPU — —%")
        self._cpu_lbl.setStyleSheet("color: #25F4EE; font-weight: 700; font-size: 12px;")
        self._cpu_chart = _SparklineChart(
            color="#25F4EE",
            y_label="CPU % (÷ cores)",
            show_footer=True,
        )
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
        )

        self._metrics_host = QWidget()
        self._metrics_grid = QGridLayout(self._metrics_host)
        self._metrics_grid.setContentsMargins(0, 0, 0, 0)
        self._metrics_grid.setHorizontalSpacing(10)
        self._metrics_grid.setVerticalSpacing(8)
        self._sync_metrics_grid_stretches(False)

        cpu_cell = QWidget()
        cpu_lay = QVBoxLayout(cpu_cell)
        cpu_lay.setContentsMargins(0, 0, 0, 0)
        cpu_lay.setSpacing(4)
        cpu_lay.addWidget(self._cpu_lbl)
        cpu_lay.addWidget(self._cpu_chart, 1)

        ram_cell = QWidget()
        ram_lay = QVBoxLayout(ram_cell)
        ram_lay.setContentsMargins(0, 0, 0, 0)
        ram_lay.setSpacing(4)
        ram_lay.addWidget(self._ram_lbl)
        ram_lay.addWidget(self._ram_chart, 1)

        self._gpu_single_cell = QWidget()
        gpu_single_lay = QVBoxLayout(self._gpu_single_cell)
        gpu_single_lay.setContentsMargins(0, 0, 0, 0)
        gpu_single_lay.setSpacing(4)
        gpu_single_lay.addWidget(self._gpu_lbl)
        gpu_single_lay.addWidget(self._gpu_chart, 1)

        self._metrics_grid.addWidget(cpu_cell, 0, 0)
        self._metrics_grid.addWidget(ram_cell, 0, 1)
        self._metrics_grid.addWidget(self._gpu_single_cell, 0, 2)
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
                "on all GPUs (and MPS cache on Apple Silicon). Frees unreachable objects and returns allocator "
                "memory to the driver; it does not force-unload models still in use by a running job.",
                "welcome",
                slide=2,
            )
        )
        self._purge_btn.clicked.connect(self._on_purge_clicked)
        self._monitor_lbl = QLabel("Monitor:")
        self._monitor_lbl.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 600;")
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
        self._title_resource_tools = QWidget()
        _tr = QHBoxLayout(self._title_resource_tools)
        _tr.setContentsMargins(0, 0, 0, 0)
        _tr.setSpacing(8)
        _tr.addWidget(self._purge_btn, 0)
        _tr.addWidget(self._monitor_lbl, 0)
        _tr.addWidget(self._gpu_monitor_combo, 1)

        self._gpu_split_inner = QWidget()
        self._gpu_split_rows_layout = QVBoxLayout(self._gpu_split_inner)
        self._gpu_split_rows_layout.setContentsMargins(0, 4, 0, 0)
        self._gpu_split_rows_layout.setSpacing(10)
        self._gpu_split_scroll = QScrollArea()
        self._gpu_split_scroll.setWidgetResizable(True)
        self._gpu_split_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._gpu_split_scroll.setWidget(self._gpu_split_inner)
        self._gpu_split_scroll.setMinimumHeight(140)
        self._gpu_split_scroll.setVisible(False)
        self.body_layout.addWidget(self._gpu_split_scroll, 1)

        self._adjust_resource_window_geometry()

        self._purge_status_lbl = QLabel("")
        self._purge_status_lbl.setStyleSheet("color: #8A96A3; font-size: 11px;")
        self._purge_status_lbl.setWordWrap(True)
        self.body_layout.addWidget(self._purge_status_lbl)
        self._sync_purge_status_visibility()

        self._gpu_monitor_combo.currentIndexChanged.connect(self._on_monitor_gpu_changed)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        self._layout_toggle_btn = styled_outline_button(
            "",
            "muted_icon",
            icon_kind="resource_expand" if self._compact_mode else "resource_compress",
            fixed=(40, 32),
            branding=branding,
        )
        self._layout_toggle_btn.setAccessibleName("Toggle usage summary vs live charts")
        self._layout_toggle_btn.clicked.connect(self._on_layout_toggle_clicked)
        # Title bar (L→R): … title … | Purge | Monitor: | combo | expand | ✕
        self.insert_title_bar_widget_before_close(self._title_resource_tools)
        self.insert_title_bar_widget_before_close(self._layout_toggle_btn)
        self._sync_layout_toggle_button()
        self._apply_compact_charts_visibility()

    def _compact_mode_from_parent(self) -> bool:
        try:
            p = self.parent()
            if p is not None and hasattr(p, "settings"):
                return bool(getattr(p.settings, "resource_graph_compact", True))
        except Exception:
            pass
        return True

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
        split = self._monitor_combo_is_split_view()
        if prev != compact:
            if not compact:
                for ch in (self._cpu_chart, self._ram_chart, self._gpu_chart):
                    ch.set_expanded_metrics(show_footer=True, min_h=128)
                if split:
                    self._rebuild_split_gpu_ui()
            else:
                for ch in (self._cpu_chart, self._ram_chart, self._gpu_chart):
                    ch.set_expanded_metrics(show_footer=False, min_h=128)
                if split:
                    self._rebuild_split_gpu_ui()
        self._apply_compact_charts_visibility()
        self._sync_purge_status_visibility()
        self._sync_layout_toggle_button()
        self._adjust_resource_window_geometry()
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
        if compact:
            split_row = 30
            split_cap = 120 + split_rows * split_row
            col_w = 120
            base_h = 168
            min_w_floor = 380
        else:
            split_row = 118
            split_cap = 560
            col_w = 200
            base_h = 460
            min_w_floor = 500
        split_h = min(split_cap, max(80, split_rows * split_row + (24 if compact else 36)))
        self._gpu_split_scroll.setMinimumHeight(split_h)
        try:
            split_visible = self._monitor_combo_is_split_view()
        except Exception:
            split_visible = False
        min_w = 72 + nc * col_w
        self.setMinimumWidth(max(min_w_floor, min_w))
        if split_visible:
            self.setMinimumHeight(base_h + split_h)
        else:
            self.setMinimumHeight(base_h)

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
                )
                if compact:
                    chart.set_expanded_metrics(show_footer=False, min_h=72)
                else:
                    chart.set_expanded_metrics(show_footer=True, min_h=100)
                cell = QWidget()
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
        split = self._monitor_combo_is_split_view()
        self._gpu_single_cell.setVisible(not split)
        self._gpu_split_scroll.setVisible(split)
        self._sync_metrics_grid_stretches(split)
        if split:
            self._rebuild_split_gpu_ui()
        else:
            self._clear_split_gpu_panel()
        self._adjust_resource_window_geometry()

    def _populate_monitor_combo(self) -> None:
        self._gpu_monitor_combo.blockSignals(True)
        self._gpu_monitor_combo.clear()
        gpus = list_cuda_gpus()
        if not gpus:
            self._gpu_monitor_combo.addItem("GPU 0", 0)
        else:
            for g in gpus:
                self._gpu_monitor_combo.addItem(f"{g.index}: {g.name}", int(g.index))
        self._gpu_monitor_combo.addItem("Split view — all GPUs", _MONITOR_COMBO_SPLIT_SENTINEL)

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
        self._apply_gpu_view_mode()
        try:
            par = self.parent()
            if par is not None and hasattr(par, "settings"):
                want = bool(getattr(par.settings, "resource_graph_compact", True))
                if want != self._compact_mode:
                    self._set_resource_view_compact(want, persist=False)
        except Exception:
            pass
        self._apply_compact_charts_visibility()
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
            show_charts = not self._compact_mode
            if show_charts:
                self._cpu_chart.push(s.process_cpu_pct)
                self._ram_chart.push(s.process_ram_pct)
            self._cpu_lbl.setText(f"CPU {s.process_cpu_pct:5.1f}%")
            self._cpu_lbl.setToolTip(
                help_tooltip_rich(
                    "Process-tree CPU (Python + subprocesses). Spikes during encode often include "
                    "FFmpeg child processes (mux/micro-clips).\n\n"
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
