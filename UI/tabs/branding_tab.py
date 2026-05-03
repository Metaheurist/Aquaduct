from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
    QColorDialog,
)

from src.core.config import BrandingSettings
from UI.help.tutorial_links import help_tooltip_rich
from UI.widgets.no_wheel_controls import NoWheelComboBox, NoWheelSpinBox
from UI.theme import PRESET_PALETTES, build_qss, resolve_palette
from UI.widgets.title_bar_outline_button import refresh_open_main_window_title_chrome


def _hex_or_default(text: str, default_hex: str) -> str:
    t = (text or "").strip()
    if not t:
        return default_hex
    return t


def _qcolor_from_hex(text: str, default_hex: str) -> QColor:
    t = (text or "").strip()
    if not t:
        t = default_hex
    if not t.startswith("#"):
        t = "#" + t
    c = QColor(t)
    if not c.isValid():
        c = QColor(default_hex)
    return c


def attach_branding_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    # Scroll wrapper so the window doesn't expand to full content height.
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    # Keep the page compact; user can scroll for the rest.
    scroll.setMinimumHeight(520)
    scroll.setMaximumHeight(700)

    content = QWidget()
    scroll.setWidget(content)
    content_lay = QVBoxLayout(content)
    content_lay.setContentsMargins(0, 0, 0, 0)

    header = QLabel("Branding (theme + logo watermark)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    content_lay.addWidget(header)

    sub = QLabel("Each section below is optional-turn on what you want.")
    sub.setStyleSheet("color: #B7B7C2;")
    sub.setToolTip(
        help_tooltip_rich(
            "Theme overrides, video/photo styling, and watermark are all optional.",
            "branding",
            slide=0,
        )
    )
    content_lay.addWidget(sub)

    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    # ---- Theme section ----
    win.brand_theme_enable = QCheckBox("Enable theme overrides")
    win.brand_theme_enable.setChecked(bool(getattr(win.settings, "branding", BrandingSettings()).theme_enabled))
    form.addRow("", win.brand_theme_enable)

    win.brand_palette_combo = NoWheelComboBox()
    # Display labels, store preset IDs.
    palette_items = [
        ("Default (TikTok dark)", "default"),
        ("Ocean", "ocean"),
        ("Sunset", "sunset"),
        ("Monochrome", "mono"),
        ("Amber night", "amber"),
        ("Dracula", "dracula"),
        ("Ember", "ember"),
        ("Forest", "forest"),
        ("Lavender", "lavender"),
        ("Nord night", "nord"),
        ("Rose", "rose"),
        ("Slate", "slate"),
        ("Custom (choose colors below)", "custom"),
    ]
    for label, pid in palette_items:
        win.brand_palette_combo.addItem(label, pid)
    cur_pid = str(getattr(getattr(win.settings, "branding", BrandingSettings()), "palette_id", "default") or "default").lower()
    idx = win.brand_palette_combo.findData(cur_pid)
    win.brand_palette_combo.setCurrentIndex(idx if idx >= 0 else 0)
    form.addRow("Palette", win.brand_palette_combo)

    def _make_color_row(label: str, *, enabled: bool, value: str, default_hex: str):
        row = QHBoxLayout()
        chk = QCheckBox(label)
        chk.setChecked(bool(enabled))
        edit = QLineEdit()
        edit.setPlaceholderText(default_hex)
        edit.setText(str(value or default_hex))
        edit.setMaximumWidth(140)

        chip = QLabel()
        chip.setFixedSize(28, 28)
        chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        def refresh_chip() -> None:
            qc = _qcolor_from_hex(edit.text(), default_hex)
            nm = qc.name()
            chip.setStyleSheet(
                f"QLabel {{ background-color: {nm}; border: 1px solid #3A3A44; border-radius: 6px; }}"
            )
            chip.setToolTip(help_tooltip_rich(f"{label}: {nm.upper()}", "branding", slide=0))

        pick = QPushButton("Pick…")
        pick.setMaximumWidth(90)

        def pick_color() -> None:
            c = _qcolor_from_hex(edit.text(), default_hex)
            chosen = QColorDialog.getColor(c, win, f"Choose {label}")
            if chosen.isValid():
                edit.setText(chosen.name().upper())

        pick.clicked.connect(pick_color)
        edit.textChanged.connect(lambda _t: refresh_chip())
        refresh_chip()

        row.addWidget(chk, 0)
        row.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(edit, 0)
        row.addWidget(pick, 0)
        row.addStretch(1)
        return chk, edit, pick, chip, row

    b = getattr(win.settings, "branding", BrandingSettings())
    defaults = PRESET_PALETTES["default"]

    win.brand_bg_chk, win.brand_bg_hex, win.brand_bg_pick, win.brand_bg_chip, bg_row = _make_color_row(
        "Background",
        enabled=bool(getattr(b, "bg_enabled", False)),
        value=str(getattr(b, "bg_hex", defaults["bg"])),
        default_hex=defaults["bg"],
    )
    form.addRow("Theme color", bg_row)

    win.brand_panel_chk, win.brand_panel_hex, win.brand_panel_pick, win.brand_panel_chip, panel_row = _make_color_row(
        "Panel",
        enabled=bool(getattr(b, "panel_enabled", False)),
        value=str(getattr(b, "panel_hex", defaults["panel"])),
        default_hex=defaults["panel"],
    )
    form.addRow("", panel_row)

    win.brand_text_chk, win.brand_text_hex, win.brand_text_pick, win.brand_text_chip, text_row = _make_color_row(
        "Text",
        enabled=bool(getattr(b, "text_enabled", False)),
        value=str(getattr(b, "text_hex", defaults["text"])),
        default_hex=defaults["text"],
    )
    form.addRow("", text_row)

    win.brand_muted_chk, win.brand_muted_hex, win.brand_muted_pick, win.brand_muted_chip, muted_row = _make_color_row(
        "Muted text",
        enabled=bool(getattr(b, "muted_enabled", False)),
        value=str(getattr(b, "muted_hex", defaults["muted"])),
        default_hex=defaults["muted"],
    )
    form.addRow("", muted_row)

    win.brand_accent_chk, win.brand_accent_hex, win.brand_accent_pick, win.brand_accent_chip, accent_row = _make_color_row(
        "Accent",
        enabled=bool(getattr(b, "accent_enabled", False)),
        value=str(getattr(b, "accent_hex", defaults["accent"])),
        default_hex=defaults["accent"],
    )
    form.addRow("", accent_row)

    win.brand_danger_chk, win.brand_danger_hex, win.brand_danger_pick, win.brand_danger_chip, danger_row = _make_color_row(
        "Danger",
        enabled=bool(getattr(b, "danger_enabled", False)),
        value=str(getattr(b, "danger_hex", defaults["danger"])),
        default_hex=defaults["danger"],
    )
    form.addRow("", danger_row)

    def _apply_preset_to_color_rows(palette_id: str, *, skip_checked_rows: bool = False) -> None:
        """Fill theme hex fields + chips from PRESET_PALETTES when a named preset is chosen."""
        pid = str(palette_id or "default").strip().lower()
        if pid == "custom":
            return
        pal = PRESET_PALETTES.get(pid, PRESET_PALETTES["default"])
        pairs = [
            (win.brand_bg_chk, win.brand_bg_hex, pal["bg"]),
            (win.brand_panel_chk, win.brand_panel_hex, pal["panel"]),
            (win.brand_text_chk, win.brand_text_hex, pal["text"]),
            (win.brand_muted_chk, win.brand_muted_hex, pal["muted"]),
            (win.brand_accent_chk, win.brand_accent_hex, pal["accent"]),
            (win.brand_danger_chk, win.brand_danger_hex, pal["danger"]),
        ]
        for chk, edit, hx in pairs:
            if skip_checked_rows and chk.isChecked():
                continue
            v = str(hx or "").strip()
            if not v.startswith("#"):
                v = "#" + v
            edit.setText(v.upper())

    # ---- Watermark section ----
    divider = QLabel(" ")
    divider.setFixedHeight(8)
    content_lay.addWidget(divider)

    # ---- Video style section (palette affects prompts + captions) ----
    vs_header = QLabel("Video look (colors also steer prompts and captions)")
    vs_header.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 6px;")
    win.brand_video_style_section_header = vs_header
    content_lay.addWidget(vs_header)

    win.brand_video_style_enable = QCheckBox("Apply branding to generated video style")
    win.brand_video_style_enable.setChecked(bool(getattr(b, "video_style_enabled", False)))
    content_lay.addWidget(win.brand_video_style_enable)

    vs_row = QHBoxLayout()
    vs_lbl = QLabel("Strength")
    vs_lbl.setStyleSheet("color: #B7B7C2;")
    vs_row.addWidget(vs_lbl)
    win.brand_video_style_strength = NoWheelComboBox()
    win.brand_video_style_strength.addItem("Subtle (readability first)", "subtle")
    win.brand_video_style_strength.addItem("Strong (dominant palette)", "strong")
    cur_strength = str(getattr(b, "video_style_strength", "subtle") or "subtle")
    idx = win.brand_video_style_strength.findData(cur_strength)
    win.brand_video_style_strength.setCurrentIndex(idx if idx >= 0 else 0)
    vs_row.addWidget(win.brand_video_style_strength)
    vs_row.addStretch(1)
    content_lay.addLayout(vs_row)

    # ---- Photo style section (layouts) ----
    photo_header = QLabel("Photo style (layouts)")
    photo_header.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 6px;")
    win.brand_photo_section_header = photo_header
    content_lay.addWidget(photo_header)

    win.brand_photo_style_enable = QCheckBox("Apply branding to photo layouts (poster/newspaper/comic)")
    win.brand_photo_style_enable.setChecked(bool(getattr(b, "photo_style_enabled", False)))
    content_lay.addWidget(win.brand_photo_style_enable)

    pf_row = QHBoxLayout()
    win.brand_photo_frame_enable = QCheckBox("Add frame border")
    win.brand_photo_frame_enable.setChecked(bool(getattr(b, "photo_frame_enabled", False)))
    pf_row.addWidget(win.brand_photo_frame_enable)
    pf_row.addStretch(1)
    content_lay.addLayout(pf_row)

    pf_form = QFormLayout()
    win.brand_photo_frame_width = NoWheelSpinBox()
    win.brand_photo_frame_width.setRange(0, 120)
    win.brand_photo_frame_width.setValue(int(getattr(b, "photo_frame_width", 24) or 24))
    pf_form.addRow("Frame width (px)", win.brand_photo_frame_width)

    win.brand_photo_paper_hex = QLineEdit()
    win.brand_photo_paper_hex.setPlaceholderText("#F2F0E9 (paper tint)")
    win.brand_photo_paper_hex.setText(str(getattr(b, "photo_paper_hex", "#F2F0E9") or "#F2F0E9"))
    pf_form.addRow("Paper tint", win.brand_photo_paper_hex)
    content_lay.addLayout(pf_form)

    wmark_header = QLabel("Logo watermark (videos)")
    wmark_header.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 6px;")
    win.brand_watermark_section_header = wmark_header
    content_lay.addWidget(wmark_header)

    win.brand_watermark_enable = QCheckBox("Watermark generated videos with a logo")
    win.brand_watermark_enable.setChecked(bool(getattr(b, "watermark_enabled", False)))
    content_lay.addWidget(win.brand_watermark_enable)

    wm_row = QHBoxLayout()
    win.brand_watermark_path = QLineEdit()
    win.brand_watermark_path.setPlaceholderText("Logo image path (.png/.jpg/.webp)…")
    win.brand_watermark_path.setText(str(getattr(b, "watermark_path", "") or ""))
    wm_row.addWidget(win.brand_watermark_path, 1)
    pick_logo = QPushButton("Browse…")

    def pick_logo_file() -> None:
        path, _ = QFileDialog.getOpenFileName(
            win,
            "Select logo image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp);;All Files (*)",
        )
        if path:
            win.brand_watermark_path.setText(path)

    pick_logo.clicked.connect(pick_logo_file)
    wm_row.addWidget(pick_logo)
    content_lay.addLayout(wm_row)

    wm_form = QFormLayout()

    win.brand_watermark_pos = NoWheelComboBox()
    for label, value in [
        ("Top left", "top_left"),
        ("Top right", "top_right"),
        ("Bottom left", "bottom_left"),
        ("Bottom right", "bottom_right"),
        ("Center", "center"),
    ]:
        win.brand_watermark_pos.addItem(label, value)
    cur_pos = str(getattr(b, "watermark_position", "top_right") or "top_right")
    idx = win.brand_watermark_pos.findData(cur_pos)
    win.brand_watermark_pos.setCurrentIndex(idx if idx >= 0 else 1)
    wm_form.addRow("Position", win.brand_watermark_pos)

    win.brand_watermark_opacity = QSlider(Qt.Orientation.Horizontal)
    win.brand_watermark_opacity.setRange(15, 75)
    win.brand_watermark_opacity.setValue(int(round(float(getattr(b, "watermark_opacity", 0.22)) * 100)))
    win.brand_watermark_opacity.setToolTip(
        help_tooltip_rich("Watermark opacity as percent of full strength.", "branding", slide=0)
    )
    wm_form.addRow("Opacity", win.brand_watermark_opacity)

    win.brand_watermark_scale = QSlider(Qt.Orientation.Horizontal)
    win.brand_watermark_scale.setRange(8, 40)
    win.brand_watermark_scale.setValue(int(round(float(getattr(b, "watermark_scale", 0.18)) * 100)))
    win.brand_watermark_scale.setToolTip(
        help_tooltip_rich("Watermark width as a percent of video frame width.", "branding", slide=0)
    )
    wm_form.addRow("Size", win.brand_watermark_scale)
    content_lay.addLayout(wm_form)

    content_lay.addLayout(form)
    content_lay.addStretch(1)

    def _branding_from_ui() -> BrandingSettings:
        return BrandingSettings(
            theme_enabled=bool(win.brand_theme_enable.isChecked()),
            palette_id=str(win.brand_palette_combo.currentData() or "default"),
            bg_enabled=bool(win.brand_bg_chk.isChecked()),
            bg_hex=_hex_or_default(win.brand_bg_hex.text(), defaults["bg"]),
            panel_enabled=bool(win.brand_panel_chk.isChecked()),
            panel_hex=_hex_or_default(win.brand_panel_hex.text(), defaults["panel"]),
            text_enabled=bool(win.brand_text_chk.isChecked()),
            text_hex=_hex_or_default(win.brand_text_hex.text(), defaults["text"]),
            muted_enabled=bool(win.brand_muted_chk.isChecked()),
            muted_hex=_hex_or_default(win.brand_muted_hex.text(), defaults["muted"]),
            accent_enabled=bool(win.brand_accent_chk.isChecked()),
            accent_hex=_hex_or_default(win.brand_accent_hex.text(), defaults["accent"]),
            danger_enabled=bool(win.brand_danger_chk.isChecked()),
            danger_hex=_hex_or_default(win.brand_danger_hex.text(), defaults["danger"]),
            watermark_enabled=bool(win.brand_watermark_enable.isChecked()),
            watermark_path=str(win.brand_watermark_path.text()).strip(),
            watermark_opacity=float(win.brand_watermark_opacity.value()) / 100.0,
            watermark_scale=float(win.brand_watermark_scale.value()) / 100.0,
            watermark_position=str(win.brand_watermark_pos.currentData() or "top_right"),
            video_style_enabled=bool(win.brand_video_style_enable.isChecked()) if hasattr(win, "brand_video_style_enable") else False,
            video_style_strength=str(win.brand_video_style_strength.currentData() or "subtle")
            if hasattr(win, "brand_video_style_strength")
            else "subtle",
            photo_style_enabled=bool(win.brand_photo_style_enable.isChecked()) if hasattr(win, "brand_photo_style_enable") else False,
            photo_frame_enabled=bool(win.brand_photo_frame_enable.isChecked()) if hasattr(win, "brand_photo_frame_enable") else False,
            photo_frame_width=int(win.brand_photo_frame_width.value()) if hasattr(win, "brand_photo_frame_width") else 24,
            photo_paper_hex=_hex_or_default(win.brand_photo_paper_hex.text(), "#F2F0E9") if hasattr(win, "brand_photo_paper_hex") else "#F2F0E9",
        )

    def _apply_live_theme() -> None:
        try:
            app = QApplication.instance()
            if app is None:
                return
            branding = _branding_from_ui()
            pal = resolve_palette(branding)
            app.setStyleSheet(build_qss(pal))
            refresh_open_main_window_title_chrome()
        except Exception:
            pass

    def _sync_enabled() -> None:
        enabled_theme = bool(win.brand_theme_enable.isChecked())
        is_custom = str(win.brand_palette_combo.currentData() or "default") == "custom"

        for chk, edit, btn, chip in [
            (win.brand_bg_chk, win.brand_bg_hex, win.brand_bg_pick, win.brand_bg_chip),
            (win.brand_panel_chk, win.brand_panel_hex, win.brand_panel_pick, win.brand_panel_chip),
            (win.brand_text_chk, win.brand_text_hex, win.brand_text_pick, win.brand_text_chip),
            (win.brand_muted_chk, win.brand_muted_hex, win.brand_muted_pick, win.brand_muted_chip),
            (win.brand_accent_chk, win.brand_accent_hex, win.brand_accent_pick, win.brand_accent_chip),
            (win.brand_danger_chk, win.brand_danger_hex, win.brand_danger_pick, win.brand_danger_chip),
        ]:
            show_custom = enabled_theme and is_custom
            chk.setEnabled(show_custom)
            row_on = show_custom and chk.isChecked()
            edit.setEnabled(row_on)
            btn.setEnabled(row_on)
            chip.setEnabled(show_custom)

        enabled_wm = bool(win.brand_watermark_enable.isChecked())
        win.brand_watermark_path.setEnabled(enabled_wm)
        pick_logo.setEnabled(enabled_wm)
        win.brand_watermark_pos.setEnabled(enabled_wm)
        win.brand_watermark_opacity.setEnabled(enabled_wm)
        win.brand_watermark_scale.setEnabled(enabled_wm)

        enabled_vs = bool(win.brand_video_style_enable.isChecked()) if hasattr(win, "brand_video_style_enable") else False
        if hasattr(win, "brand_video_style_strength"):
            win.brand_video_style_strength.setEnabled(enabled_vs)

    def _on_palette_changed(_i: int) -> None:
        _apply_preset_to_color_rows(str(win.brand_palette_combo.currentData() or "default"), skip_checked_rows=False)
        _sync_enabled()
        _apply_live_theme()

    win.brand_palette_combo.currentIndexChanged.connect(_on_palette_changed)

    # Live apply + enablement wiring
    for sig_src in [
        win.brand_theme_enable,
        win.brand_bg_chk,
        win.brand_panel_chk,
        win.brand_text_chk,
        win.brand_muted_chk,
        win.brand_accent_chk,
        win.brand_danger_chk,
        win.brand_bg_hex,
        win.brand_panel_hex,
        win.brand_text_hex,
        win.brand_muted_hex,
        win.brand_accent_hex,
        win.brand_danger_hex,
        win.brand_video_style_enable,
    ]:
        try:
            if isinstance(sig_src, QLineEdit):
                sig_src.textChanged.connect(lambda _t: (_sync_enabled(), _apply_live_theme()))
            else:
                sig_src.toggled.connect(lambda _v: (_sync_enabled(), _apply_live_theme()))  # type: ignore[attr-defined]
        except Exception:
            try:
                sig_src.currentIndexChanged.connect(lambda _i: (_sync_enabled(), _apply_live_theme()))  # type: ignore[attr-defined]
            except Exception:
                pass

    win.brand_watermark_enable.toggled.connect(lambda _v: _sync_enabled())
    win.brand_watermark_path.textChanged.connect(lambda _t: None)
    win.brand_watermark_pos.currentIndexChanged.connect(lambda _i: None)
    win.brand_watermark_opacity.valueChanged.connect(lambda _v: None)
    win.brand_watermark_scale.valueChanged.connect(lambda _v: None)
    win.brand_video_style_strength.currentIndexChanged.connect(lambda _i: None)

    if str(win.brand_palette_combo.currentData() or "default") != "custom":
        _apply_preset_to_color_rows(str(win.brand_palette_combo.currentData() or "default"), skip_checked_rows=True)

    _sync_enabled()
    _apply_live_theme()

    lay.addWidget(scroll)
    win.tabs.addTab(w, "Branding")

