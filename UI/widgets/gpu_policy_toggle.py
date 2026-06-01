"""Two-segment Auto | Select GPU toggle (My PC tab)."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from UI.help.tutorial_links import help_tooltip_rich
from UI.widgets.themed_toggle import ThemedToggle


class GpuPolicyToggle(ThemedToggle):
    """
    Segmented control: **Auto** vs **Select GPU** (pins one CUDA device).

    Mirrors :class:`UI.widgets.media_mode_toggle.MediaModeToggle` API shape:
    ``currentIndex()``, ``setCurrentIndex()``, ``currentIndexChanged``, ``currentData()``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            left_label="Auto",
            right_label="Select GPU",
            left_value="auto",
            right_value="single",
            left_acc="Automatic GPU policy",
            right_acc="Pin all stages to one GPU",
            accessible_name="GPU policy",
            tooltip_body=(
                "Auto: multi-GPU stage routing (script vs diffusion may use different devices; VRAM is not pooled). "
                "Select GPU: pin all local stages to the device below. "
                "If AQUADUCT_CUDA_DEVICE is set in the environment, it overrides the saved policy."
            ),
            tooltip_topic="my_pc",
            tooltip_slide=0,
            object_name_root="gpuPolicyToggleRoot",
            object_name_shell="gpuPolicyToggleShell",
            object_name_left="gpuSegAuto",
            object_name_right="gpuSegSingle",
            default_index=0,
            min_button_width=88,
            min_button_height=32,
            font_size_px=12,
            button_padding_css="5px 10px",
            left_tooltip=help_tooltip_rich(
                "LLM tends toward the compute-heuristic CUDA device; image/video diffusion uses the max-VRAM GPU. "
                "If both would use the same GPU, the LLM moves to the best other CUDA device so both cards stay busy. "
                "VRAM is not merged across GPUs.",
                "my_pc",
                slide=0,
            ),
            right_tooltip=help_tooltip_rich(
                "All local pipeline stages use the CUDA index chosen in Device.",
                "my_pc",
                slide=0,
            ),
            parent=parent,
        )
