"""Two-segment Photo | Video toggle (centered in the custom title bar)."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from UI.widgets.themed_toggle import ThemedToggle


class MediaModeToggle(ThemedToggle):
    """
    Segmented control with **Photo** and **Video** labels.

    Mimics the small part of ``QComboBox`` used by settings/main:
    ``currentData()``, ``setCurrentIndex()``, ``currentIndexChanged``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            left_label="Photo",
            right_label="Video",
            left_value="photo",
            right_value="video",
            left_acc="Photo mode",
            right_acc="Video mode",
            accessible_name="Media mode",
            tooltip_body=(
                "Video: render MP4 shorts. Photo: generate still images and layouts (Picture tab)."
            ),
            tooltip_topic="run",
            tooltip_slide=2,
            object_name_root="mediaModeToggleRoot",
            object_name_shell="mediaModeToggleShell",
            object_name_left="modeSegPhoto",
            object_name_right="modeSegVideo",
            default_index=1,
            min_button_width=80,
            min_button_height=32,
            font_size_px=13,
            button_padding_css="6px 14px",
            parent=parent,
        )
