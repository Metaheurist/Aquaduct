from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QFormLayout, QFrame, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from src.hardware import get_hardware_info, rate_model_fit_for_repo
from src.model_manager import model_options


def _fit_colors(marker: str) -> tuple[QColor, QColor]:
    """
    Returns (bg, fg) for the fit marker.
    """
    marker = (marker or "").upper().strip()
    if marker == "EXCELLENT":
        return QColor("#12381F"), QColor("#CFFFE0")
    if marker == "OK":
        return QColor("#0F2F45"), QColor("#D7F1FF")
    if marker == "RISKY":
        return QColor("#3C2D12"), QColor("#FFE7C2")
    if marker == "NO_GPU":
        return QColor("#3B1414"), QColor("#FFD2D2")
    return QColor("#2A2A2F"), QColor("#E6E6F0")


def attach_my_pc_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("My PC (hardware + model fit)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    info = get_hardware_info()
    sub = QLabel("Summary + what models should fit on this machine.")
    sub.setStyleSheet("color: #B7B7C2;")
    lay.addWidget(sub)

    card = QFrame()
    card.setFrameShape(QFrame.Shape.StyledPanel)
    card.setStyleSheet("QFrame { background: #14141A; border: 1px solid #2A2A34; border-radius: 10px; }")
    card_lay = QVBoxLayout(card)

    form = QFormLayout()
    form.setLabelAlignment(form.labelAlignment() | 0x2)  # AlignRight
    os_lbl = QLabel(info.os)
    cpu_lbl = QLabel(info.cpu)
    ram_lbl = QLabel(f"{info.ram_gb:.1f} GB" if info.ram_gb else "(not detected)")
    gpu_lbl = QLabel(info.gpu_name or "(not detected)")
    vram_lbl = QLabel(f"{info.vram_gb:.1f} GB" if info.vram_gb else "(not detected)")
    for v in (os_lbl, cpu_lbl, ram_lbl, gpu_lbl, vram_lbl):
        v.setStyleSheet("font-weight: 600;")

    form.addRow("OS", os_lbl)
    form.addRow("CPU", cpu_lbl)
    form.addRow("RAM", ram_lbl)
    form.addRow("GPU", gpu_lbl)
    form.addRow("VRAM", vram_lbl)
    card_lay.addLayout(form)

    hint = QLabel(
        "Rule of thumb: ≥ 8GB VRAM is the sweet spot for SDXL Turbo; bigger LLMs/images are slower and may OOM. "
        "The pipeline unloads models between stages to reduce peak VRAM."
    )
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #B7B7C2; margin-top: 6px;")
    card_lay.addWidget(hint)
    lay.addWidget(card)

    legend = QLabel(
        "Fit legend: EXCELLENT (green) • OK (blue) • RISKY (amber) • NO_GPU (red) • UNKNOWN (gray)"
    )
    legend.setStyleSheet("color: #B7B7C2; margin-top: 8px;")
    lay.addWidget(legend)

    table = QTableWidget()
    opts = model_options()
    table.setColumnCount(5)
    table.setHorizontalHeaderLabels(["Kind", "Model", "Speed", "Fit", "Why"])
    table.setRowCount(len(opts))
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

    for r, opt in enumerate(opts):
        marker, why = rate_model_fit_for_repo(
            kind=opt.kind,
            speed=opt.speed,
            repo_id=opt.repo_id,
            pair_image_repo_id=getattr(opt, "pair_image_repo_id", "") or "",
            vram_gb=info.vram_gb,
            ram_gb=info.ram_gb,
        )
        bg, fg = _fit_colors(marker)
        table.setItem(r, 0, QTableWidgetItem(opt.kind))
        table.setItem(r, 1, QTableWidgetItem(opt.repo_id))
        table.setItem(r, 2, QTableWidgetItem(opt.speed))
        fit_item = QTableWidgetItem(marker)
        fit_item.setBackground(bg)
        fit_item.setForeground(fg)
        table.setItem(r, 3, fit_item)
        table.setItem(r, 4, QTableWidgetItem(why))

    table.resizeColumnsToContents()
    lay.addWidget(table, 1)

    win.tabs.addTab(w, "My PC")
