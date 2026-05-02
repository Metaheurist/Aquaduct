from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.models.model_tiers import api_tier_for_model, tier_badge, tier_label, tier_sort_rank
from src.settings.api_model_catalog import (
    default_models_for_provider,
    default_openai_compatible_base_url_for_llm,
    providers_for_role,
    uses_openai_chat_protocol_for_llm,
)
from UI.help.tutorial_links import help_tooltip_rich, help_tooltip_rich_unless_already
from UI.widgets.no_wheel_controls import NoWheelComboBox


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
    pid = str(provider or "").strip().lower()
    models = list(default_models_for_provider(pid, role))  # type: ignore[arg-type]
    sm = (saved_model or "").strip()
    if sm and sm not in models:
        models.append(sm)
    models = sorted(models, key=lambda m: (tier_sort_rank(api_tier_for_model(pid, m)), m.lower()))

    mdl = QStandardItemModel(model_combo)
    last_rank = -1
    per_rank: dict[int, int] = {}
    for m in models:
        tr = api_tier_for_model(pid, m)
        rk = tier_sort_rank(tr)
        if rk != last_rank:
            last_rank = rk
            h = QStandardItem(tier_label(tr))
            h.setEnabled(False)
            h.setSelectable(False)
            hf = QFont()
            hf.setBold(True)
            h.setFont(hf)
            mdl.appendRow(h)
            per_rank[rk] = 0
        per_rank[rk] = per_rank.get(rk, 0) + 1
        n = per_rank[rk]
        row = QStandardItem(f"{n:02d}. {m}")
        row.setData(m, Qt.ItemDataRole.UserRole)
        row.setToolTip(
            help_tooltip_rich(
                f"Tier: {tier_label(tr)}\nModel: {m}\nProvider: {pid or '(none)'}",
                "api_social",
                slide=1,
            )
        )
        mdl.appendRow(row)

    model_combo.blockSignals(True)
    model_combo.setEditable(True)
    model_combo.setModel(mdl)
    if sm:
        idx = model_combo.findData(sm, Qt.ItemDataRole.UserRole)
        if idx >= 0:
            model_combo.setCurrentIndex(idx)
        else:
            model_combo.setEditText(sm)
    model_combo.blockSignals(False)
    _sync_api_model_combo_tip(model_combo, pid)


def _sync_api_model_combo_tip(model_combo: QComboBox, provider_id: str) -> None:
    pid = str(provider_id or "").strip().lower()
    idx = model_combo.currentIndex()
    if idx < 0:
        model_combo.setToolTip(
            help_tooltip_rich("Select a model or type a custom model / version id.", "api_social", slide=1)
        )
        return
    tip = model_combo.itemData(idx, Qt.ItemDataRole.ToolTipRole)
    if tip is not None and str(tip).strip():
        model_combo.setToolTip(help_tooltip_rich_unless_already(str(tip), "api_social", slide=1))
        return
    mid = str(model_combo.itemData(idx) or model_combo.currentText() or "").strip()
    if not mid:
        model_combo.setToolTip(help_tooltip_rich("API model (editable).", "api_social", slide=1))
        return
    tr = api_tier_for_model(pid, mid)
    model_combo.setToolTip(
        help_tooltip_rich(
            f"Tier: {tier_label(tr)} ({tier_badge(tr).strip('[]')})\nModel: {mid}\nProvider: {pid or '(none)'}",
            "api_social",
            slide=1,
        )
    )


def build_generation_api_panel(win) -> QWidget:
    root = QGroupBox("Cloud generation (when Model tab is set to API)")
    root.setToolTip(
        help_tooltip_rich(
            "Used when Model tab is set to API. Env overrides saved keys: OPENAI_API_KEY, GEMINI_API_KEY, "
            "GROQ_API_KEY, TOGETHER_API_KEY, MISTRAL_API_KEY, OPENROUTER_API_KEY, DEEPSEEK_API_KEY, XAI_API_KEY, "
            "FIREWORKS_API_KEY, CEREBRAS_API_KEY, NEBIUS_API_KEY, SILICONFLOW_API_KEY, KLING_ACCESS_KEY, KLING_SECRET_KEY, "
            "MAGIC_HOUR_API_KEY, INWORLD_API_KEY, REPLICATE_API_TOKEN, ELEVENLABS_API_KEY, …",
            "api_social",
            slide=1,
        )
    )
    root.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    root.setMinimumWidth(420)
    outer = QVBoxLayout(root)

    keys_row = QFormLayout()
    win.api_gen_openai_key = QLineEdit()
    win.api_gen_openai_key.setEchoMode(QLineEdit.EchoMode.Password)
    win.api_gen_openai_key.setPlaceholderText("Paste API key—or set OPENAI_API_KEY in your environment")
    win.api_gen_openai_key.setText(str(getattr(win.settings, "api_openai_key", "") or ""))
    keys_row.addRow("OpenAI / LLM API key", win.api_gen_openai_key)

    win.api_gen_replicate_token = QLineEdit()
    win.api_gen_replicate_token.setEchoMode(QLineEdit.EchoMode.Password)
    win.api_gen_replicate_token.setPlaceholderText("Replicate token—or set REPLICATE_API_TOKEN")
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
        prov = NoWheelComboBox()
        _set_combo_data(prov, _provider_items(role))
        rc = _rcfg(role)
        cur_p = str(getattr(rc, "provider", "") or "").strip().lower() if rc is not None else ""
        ip = prov.findData(cur_p)
        prov.setCurrentIndex(ip if ip >= 0 else 0)
        mod = NoWheelComboBox()
        _refill_model_combo(mod, role=role, provider=cur_p, saved_model=str(getattr(rc, "model", "") or "") if rc is not None else "")
        base: QLineEdit | None = None
        org: QLineEdit | None = None
        voice: QLineEdit | None = None
        if role == "llm":
            base = QLineEdit()
            base.setPlaceholderText("Custom API base URL (leave blank for OpenAI)")
            base.setText(str(getattr(_rcfg("llm"), "base_url", "") or "") if _rcfg("llm") is not None else "")
            org = QLineEdit()
            org.setPlaceholderText("Org ID (optional, OpenAI-style)")
            org.setText(str(getattr(_rcfg("llm"), "org_id", "") or "") if _rcfg("llm") is not None else "")
            fl.addRow("Base URL", base)
            fl.addRow("Organization", org)
        if role == "voice":
            voice = QLineEdit()
            voice.setPlaceholderText("Provider’s voice or speaker id")
            voice.setText(str(getattr(_rcfg("voice"), "voice_id", "") or "") if _rcfg("voice") is not None else "")
            fl.addRow("Voice / speaker id", voice)

        def _on_prov_change(_i: int) -> None:
            pid = str(prov.currentData() or "").strip().lower()
            _refill_model_combo(mod, role=role, provider=pid, saved_model="")
            if role == "llm" and base is not None and pid and uses_openai_chat_protocol_for_llm(pid):
                if not base.text().strip():
                    du = default_openai_compatible_base_url_for_llm(pid)
                    if du:
                        base.setText(du)
            if hasattr(win, "_sync_api_gen_row_states"):
                win._sync_api_gen_row_states()

        prov.currentIndexChanged.connect(_on_prov_change)
        fl.addRow("Provider", prov)
        fl.addRow("Model", mod)
        mod.currentIndexChanged.connect(
            lambda _i, m=mod, p=prov: _sync_api_model_combo_tip(m, str(p.currentData() or ""))
        )
        outer.addWidget(box)
        return prov, mod, base, org, voice

    win.api_gen_llm_provider, win.api_gen_llm_model, win.api_gen_llm_base, win.api_gen_llm_org, _ = _role_block(
        "LLM API (script)", "llm"
    )
    win.api_gen_image_provider, win.api_gen_image_model, _, _, _ = _role_block("Image API (stills)", "image")
    win.api_gen_video_provider, win.api_gen_video_model, _, _, _ = _role_block("Video API (Pro / Replicate)", "video")
    win.api_gen_voice_provider, win.api_gen_voice_model, _, _, win.api_gen_voice_id = _role_block("Voice API", "voice")

    hint = QLabel("Tip: you can set API keys as environment variables instead—hover for a list.")
    hint.setWordWrap(True)
    hint.setStyleSheet("color:#9BB0C4;font-size:12px;")
    hint.setToolTip(
        help_tooltip_rich(
            "Common names: OPENAI_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, REPLICATE_API_TOKEN, ELEVENLABS_API_KEY, "
            "plus provider-specific keys (see this panel’s group tooltip for the full set). Env wins over saved fields.",
            "api_social",
            slide=1,
        )
    )
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
