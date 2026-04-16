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
    QSlider,
    QVBoxLayout,
    QWidget,
    QColorDialog,
)

from src.config import BrandingSettings
from UI.theme import PRESET_PALETTES, build_qss, resolve_palette


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

    header = QLabel("Branding (theme + logo watermark)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    sub = QLabel("All options are optional. Enable the checkbox to apply an override.")
    sub.setStyleSheet("color: #B7B7C2;")
    lay.addWidget(sub)

    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    # ---- Theme section ----
    win.brand_theme_enable = QCheckBox("Enable theme overrides")
    win.brand_theme_enable.setChecked(bool(getattr(win.settings, "branding", BrandingSettings()).theme_enabled))
    form.addRow("", win.brand_theme_enable)

    win.brand_palette_combo = QComboBox()
    # Display labels, store preset IDs.
    palette_items = [
        ("Default (TikTok dark)", "default"),
        ("Ocean", "ocean"),
        ("Sunset", "sunset"),
        ("Monochrome", "mono"),
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
            chip.setToolTip(f"{label}: {nm.upper()}")

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

    # ---- Watermark section ----
    divider = QLabel(" ")
    divider.setFixedHeight(8)
    lay.addWidget(divider)

    # ---- Video style section (palette affects prompts + captions) ----
    vs_header = QLabel("Video style (palette → prompts + captions)")
    vs_header.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 6px;")
    lay.addWidget(vs_header)

    win.brand_video_style_enable = QCheckBox("Apply branding to generated video style")
    win.brand_video_style_enable.setChecked(bool(getattr(b, "video_style_enabled", False)))
    lay.addWidget(win.brand_video_style_enable)

    vs_row = QHBoxLayout()
    vs_lbl = QLabel("Strength")
    vs_lbl.setStyleSheet("color: #B7B7C2;")
    vs_row.addWidget(vs_lbl)
    win.brand_video_style_strength = QComboBox()
    win.brand_video_style_strength.addItem("Subtle (readability first)", "subtle")
    win.brand_video_style_strength.addItem("Strong (dominant palette)", "strong")
    cur_strength = str(getattr(b, "video_style_strength", "subtle") or "subtle")
    idx = win.brand_video_style_strength.findData(cur_strength)
    win.brand_video_style_strength.setCurrentIndex(idx if idx >= 0 else 0)
    vs_row.addWidget(win.brand_video_style_strength)
    vs_row.addStretch(1)
    lay.addLayout(vs_row)

    wmark_header = QLabel("Logo watermark (videos)")
    wmark_header.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 6px;")
    lay.addWidget(wmark_header)

    win.brand_watermark_enable = QCheckBox("Watermark generated videos with a logo")
    win.brand_watermark_enable.setChecked(bool(getattr(b, "watermark_enabled", False)))
    lay.addWidget(win.brand_watermark_enable)

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
    lay.addLayout(wm_row)

    wm_form = QFormLayout()

    win.brand_watermark_pos = QComboBox()
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
    win.brand_watermark_opacity.setToolTip("Opacity (%)")
    wm_form.addRow("Opacity", win.brand_watermark_opacity)

    win.brand_watermark_scale = QSlider(Qt.Orientation.Horizontal)
    win.brand_watermark_scale.setRange(8, 40)
    win.brand_watermark_scale.setValue(int(round(float(getattr(b, "watermark_scale", 0.18)) * 100)))
    win.brand_watermark_scale.setToolTip("Size (% of video width)")
    wm_form.addRow("Size", win.brand_watermark_scale)
    lay.addLayout(wm_form)

    lay.addLayout(form)
    lay.addStretch(1)

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
        )

    def _apply_live_theme() -> None:
        try:
            app = QApplication.instance()
            if app is None:
                return
            branding = _branding_from_ui()
            pal = resolve_palette(branding)
            app.setStyleSheet(build_qss(pal))
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

    # Live apply + enablement wiring
    for sig_src in [
        win.brand_theme_enable,
        win.brand_palette_combo,
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

    _sync_enabled()
    _apply_live_theme()

    win.tabs.addTab(w, "Branding")

