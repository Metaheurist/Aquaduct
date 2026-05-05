"""Two-segment Default | External toggle for where Hugging Face model snapshots live."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from UI.widgets.themed_toggle import ThemedToggle


class ModelsStorageModeToggle(ThemedToggle):
    """
    Segmented control: **Default** (``.Aquaduct_data/models``) vs **External** (custom folder).
    Matches ``ModelExecutionModeToggle`` API: ``currentIndexChanged``, ``currentData()``, ``setCurrentIndex``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            left_label="Default",
            right_label="External",
            left_value="default",
            right_value="external",
            left_acc="Use project .Aquaduct_data/models",
            right_acc="Use a custom folder for model snapshots",
            accessible_name="Models storage location",
            tooltip_body=(
                "Default: project .Aquaduct_data/models. External: another drive or shared cache."
            ),
            tooltip_topic="models",
            tooltip_slide=3,
            object_name_root="modelsStorageModeToggleRoot",
            object_name_shell="modelsStorageModeToggleShell",
            object_name_left="modeSegDefault",
            object_name_right="modeSegExternal",
            default_index=0,
            min_button_width=88,
            min_button_height=32,
            font_size_px=13,
            button_padding_css="6px 14px",
            parent=parent,
        )
