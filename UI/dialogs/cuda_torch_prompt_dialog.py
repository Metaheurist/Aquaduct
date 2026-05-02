"""First-run–style prompt: NVIDIA GPU visible but CPU-only PyTorch installed."""

from __future__ import annotations

from typing import Literal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel

from UI.dialogs.frameless_dialog import FramelessDialog
from UI.help.tutorial_links import help_tooltip_rich
from UI.widgets.title_bar_outline_button import styled_outline_button

CudaTorchChoice = Literal["install", "later", "never"]


def prompt_cuda_torch_mismatch_choice(parent, *, suggestion: str | None = None) -> CudaTorchChoice:
    """
    Modal: offer to launch the CUDA PyTorch installer, postpone, or never remind (persisted by caller).

    ``suggestion`` may be full multiline hint (e.g. pip command); shown in a monospace detail label.
    """
    d = FramelessDialog(parent, title="GPU detected — CUDA PyTorch missing")
    d.setMinimumWidth(540)

    body = QLabel(
        "<p style=\"margin-bottom:10px;\">Windows / Linux detected an NVIDIA GPU, but this environment has "
        "<b>CPU-only PyTorch</b>. Local inference will not use CUDA until matching GPU wheels are installed.</p>"
        "<p style=\"margin-bottom:10px;\">Choose <b>Install CUDA PyTorch</b> to download here (large files; the next "
        "window shows live pip progress). <b>Restart Aquaduct</b> after a successful install so Python loads the new build.</p>"
        "<p>You can also run the same step from the Model tab → <b>Install dependencies</b>.</p>"
    )
    body.setWordWrap(True)
    body.setTextFormat(Qt.TextFormat.RichText)
    body.setOpenExternalLinks(True)
    body.setStyleSheet("color: #B7B7C2; font-size: 12px;")
    d.body_layout.addWidget(body)

    if suggestion and suggestion.strip():
        hint = QLabel(suggestion.strip())
        hint.setWordWrap(True)
        hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        hint.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 10px; color: #8A96A3; "
            "background-color: rgba(255,255,255,0.04); padding: 8px; border-radius: 6px;"
        )
        d.body_layout.addWidget(hint)

    tip = QLabel("Same install as Model → Install dependencies → PyTorch step (CUDA index is chosen automatically).")
    tip.setWordWrap(True)
    tip.setStyleSheet("color: #6A7080; font-size: 11px;")
    tip.setToolTip(
        help_tooltip_rich(
            "Blackwell / RTX 50-series uses the cu128 index when detected; older NVIDIA GPUs typically use cu124.",
            "models",
            slide=2,
        )
    )
    d.body_layout.addWidget(tip)

    picked: dict[str, CudaTorchChoice] = {"v": "later"}

    row = QHBoxLayout()

    btn_never = styled_outline_button("Don't ask again", "muted_icon", min_width=132)

    btn_later = styled_outline_button("Not now", "muted_icon", min_width=96)

    btn_install = styled_outline_button("Install CUDA PyTorch", "accent_icon", min_width=180)

    def _never() -> None:
        picked["v"] = "never"
        d.accept()

    def _later() -> None:
        picked["v"] = "later"
        d.reject()

    def _install() -> None:
        picked["v"] = "install"
        d.accept()

    btn_never.clicked.connect(_never)
    btn_later.clicked.connect(_later)
    btn_install.clicked.connect(_install)

    row.addWidget(btn_never, 0, Qt.AlignmentFlag.AlignLeft)
    row.addStretch(1)
    row.addWidget(btn_later)
    row.addWidget(btn_install)
    d.body_layout.addLayout(row)

    btn_install.setDefault(True)
    btn_install.setAutoDefault(True)

    d.exec()
    return picked["v"]
