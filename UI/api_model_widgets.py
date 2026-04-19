from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from src.settings.api_model_catalog import default_models_for_provider, providers_for_role


def _set_combo_data(combo: QComboBox, items: list[tuple[str, str]]) -> None:
    combo.blockSignals(True)
    combo.clear()
    for label, data in items:
        combo.addItem(label, data)
    combo.blockSignals(False)


def _provider_items(role: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = [("(not set)", "")]
    for p in providers_for_role(role):  # type: ignore[arg-type]
        out.append((p.display_name, p.id))
    return out


def _refill_model_combo(model_combo: QComboBox, *, role: str, provider: str, saved_model: str = "") -> None:
    models = default_models_for_provider(provider, role)  # type: ignore[arg-type]
    model_combo.blockSignals(True)
    model_combo.clear()
    model_combo.setEditable(True)
    for m in models:
        model_combo.addItem(m, m)
    if saved_model and model_combo.findText(saved_model) < 0:
        model_combo.insertItem(0, saved_model, saved_model)
    if saved_model:
        idx = model_combo.findData(saved_model)
        if idx >= 0:
            model_combo.setCurrentIndex(idx)
        else:
            model_combo.setEditText(saved_model)
    model_combo.blockSignals(False)


def build_generation_api_panel(win) -> QWidget:
    root = QGroupBox("Generation APIs (API execution mode)")
    root.setToolTip("Used when Model tab is set to API. Keys: OPENAI_API_KEY and REPLICATE_API_TOKEN override saved values.")
    outer = QVBoxLayout(root)

    keys_row = QFormLayout()
    win.api_gen_openai_key = QLineEdit()
    win.api_gen_openai_key.setEchoMode(QLineEdit.EchoMode.Password)
    win.api_gen_openai_key.setPlaceholderText("sk-… (optional if OPENAI_API_KEY is set)")
    win.api_gen_openai_key.setText(str(getattr(win.settings, "api_openai_key", "") or ""))
    keys_row.addRow("OpenAI API key", win.api_gen_openai_key)

    win.api_gen_replicate_token = QLineEdit()
    win.api_gen_replicate_token.setEchoMode(QLineEdit.EchoMode.Password)
    win.api_gen_replicate_token.setPlaceholderText("r8_… (optional if REPLICATE_API_TOKEN is set)")
    win.api_gen_replicate_token.setText(str(getattr(win.settings, "api_replicate_token", "") or ""))
    keys_row.addRow("Replicate API token", win.api_gen_replicate_token)
    outer.addLayout(keys_row)

    am = getattr(win.settings, "api_models", None)

    def _rcfg(role_name: str):
        if am is None:
            return None
        return getattr(am, role_name, None)

    def _role_block(title: str, role: str) -> tuple[QComboBox, QComboBox, QLineEdit | None, QLineEdit | None, QLineEdit | None]:
        box = QGroupBox(title)
        fl = QFormLayout(box)
        prov = QComboBox()
        _set_combo_data(prov, _provider_items(role))
        rc = _rcfg(role)
        cur_p = str(getattr(rc, "provider", "") or "").strip().lower() if rc is not None else ""
        ip = prov.findData(cur_p)
        prov.setCurrentIndex(ip if ip >= 0 else 0)
        mod = QComboBox()
        _refill_model_combo(mod, role=role, provider=cur_p, saved_model=str(getattr(rc, "model", "") or "") if rc is not None else "")
        base: QLineEdit | None = None
        org: QLineEdit | None = None
        voice: QLineEdit | None = None
        if role == "llm":
            base = QLineEdit()
            base.setPlaceholderText("Optional base URL (default https://api.openai.com/v1)")
            base.setText(str(getattr(_rcfg("llm"), "base_url", "") or "") if _rcfg("llm") is not None else "")
            org = QLineEdit()
            org.setPlaceholderText("Optional OpenAI-Organization")
            org.setText(str(getattr(_rcfg("llm"), "org_id", "") or "") if _rcfg("llm") is not None else "")
            fl.addRow("Base URL", base)
            fl.addRow("Organization", org)
        if role == "voice":
            voice = QLineEdit()
            voice.setPlaceholderText("Voice id (OpenAI: alloy, … / ElevenLabs: voice id)")
            voice.setText(str(getattr(_rcfg("voice"), "voice_id", "") or "") if _rcfg("voice") is not None else "")
            fl.addRow("Voice / speaker id", voice)

        def _on_prov_change(_i: int) -> None:
            pid = str(prov.currentData() or "").strip().lower()
            _refill_model_combo(mod, role=role, provider=pid, saved_model="")
            if hasattr(win, "_sync_api_gen_row_states"):
                win._sync_api_gen_row_states()

        prov.currentIndexChanged.connect(_on_prov_change)
        fl.addRow("Provider", prov)
        fl.addRow("Model", mod)
        outer.addWidget(box)
        return prov, mod, base, org, voice

    win.api_gen_llm_provider, win.api_gen_llm_model, win.api_gen_llm_base, win.api_gen_llm_org, _ = _role_block(
        "LLM API (script)", "llm"
    )
    win.api_gen_image_provider, win.api_gen_image_model, _, _, _ = _role_block("Image API (stills)", "image")
    win.api_gen_video_provider, win.api_gen_video_model, _, _, _ = _role_block("Video API (Pro / Replicate)", "video")
    win.api_gen_voice_provider, win.api_gen_voice_model, _, _, win.api_gen_voice_id = _role_block("Voice API", "voice")

    hint = QLabel("Env overrides: OPENAI_API_KEY, REPLICATE_API_TOKEN (take precedence over saved keys).")
    hint.setWordWrap(True)
    hint.setStyleSheet("color:#9BB0C4;font-size:12px;")
    outer.addWidget(hint)

    def _sync_rows() -> None:
        if hasattr(win, "_sync_api_gen_row_states"):
            win._sync_api_gen_row_states()

    win.api_gen_openai_key.textChanged.connect(lambda _t: _sync_rows())
    win.api_gen_replicate_token.textChanged.connect(lambda _t: _sync_rows())
    for w in (
        win.api_gen_llm_provider,
        win.api_gen_image_provider,
        win.api_gen_video_provider,
        win.api_gen_voice_provider,
    ):
        w.currentIndexChanged.connect(lambda _i: _sync_rows())
    return root
