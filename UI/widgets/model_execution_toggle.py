"""Two-segment Local | API toggle for the Model tab (replaces a plain combo for clarity)."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from UI.widgets.themed_toggle import ThemedToggle


class ModelExecutionModeToggle(ThemedToggle):
    """
    Segmented control with **Local** and **API** labels. Mimics the small part of ``QComboBox``
    used by settings/main: ``currentData()``, ``setCurrentIndex()``, ``currentIndexChanged``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            left_label="Local",
            right_label="API",
            left_value="local",
            right_value="api",
            left_acc="Local models on this PC",
            right_acc="Cloud APIs for generation",
            accessible_name="Model execution mode",
            tooltip_body="Local: Hugging Face weights on this PC. API: cloud script / images / voice.",
            tooltip_topic="models",
            tooltip_slide=1,
            object_name_root="modelExecutionModeToggleRoot",
            object_name_shell="modelExecutionModeToggleShell",
            object_name_left="modeSegLocal",
            object_name_right="modeSegApi",
            default_index=0,
            min_button_width=80,
            min_button_height=32,
            font_size_px=13,
            button_padding_css="6px 14px",
            parent=parent,
        )
