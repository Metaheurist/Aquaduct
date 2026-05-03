"""Frameless LLM playground: chat with the selected script model (local or API).

Unload / persistence order (see plan §13):

1. Cancel in-flight worker and wait (bounded) for the QThread.
2. Dispose local causal LM from ``_llm_holder`` if loaded (frees VRAM).
3. Persist encrypted transcript (best-effort).
4. ``MainWindow`` is notified via ``_on_llm_chat_closed`` so the dialog ref is cleared.

``MainWindow.closeEvent`` calls ``LLMChatDialog.close()`` so this runs before app exit.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from UI.dialogs.frameless_dialog import FramelessDialog
from UI.widgets.title_bar_outline_button import styled_outline_button

from src.content.brain import _dispose_causal_lm_pair, _infer_text_with_optional_holder
from src.core.config import AppSettings, get_paths
from src.platform.openai_client import OpenAIRequestError, build_openai_client_from_settings
from src.runtime.model_backend import is_api_mode, provider_has_key
from src.util.llm_chat_transcript_store import delete_transcript, load_transcript, save_transcript


DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant for Aquaduct, a short-form desktop video app. "
    "Answer clearly and concisely in the user's language when obvious. "
    "If the user asks for JSON or structured output, comply."
)

_MAX_MESSAGES_ROLL = 12
_MAX_TRANSCRIPT_PERSIST = 200


class _EnterSendingPlainText(QPlainTextEdit):
    send_requested = pyqtSignal()

    def keyPressEvent(self, e) -> None:  # type: ignore[override]
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(e)
                return
            self.send_requested.emit()
            e.accept()
            return
        super().keyPressEvent(e)


def resolve_chat_target(win) -> tuple[str, str, str, str | None]:
    """
    Returns (mode, display_label, model_key, error_or_none).
    mode is 'api' or 'local'.
    """
    settings: AppSettings = win.settings
    if is_api_mode(settings):
        am = getattr(settings, "api_models", None)
        llm = getattr(am, "llm", None) if am is not None else None
        prov = str(getattr(llm, "provider", "") or "").strip().lower() if llm else ""
        mdl = str(getattr(llm, "model", "") or "").strip() if llm else ""
        if not prov or not mdl:
            return "api", "", "", "API mode: configure the LLM provider and model on the API tab."
        if not provider_has_key(settings, prov):
            return "api", "", "", f"API mode: missing API key for provider “{prov}” (API tab)."
        label = f"API · {prov} / {mdl}"
        return "api", label, mdl, None

    repo = ""
    if hasattr(win, "llm_combo"):
        try:
            repo = str(win.llm_combo.currentData() or "").strip()
        except Exception:
            repo = ""
    if not repo:
        repo = str(getattr(settings, "llm_model_id", "") or "").strip()
    if not repo:
        return "local", "", "", "Choose a script (LLM) model on the Model tab."
    label = f"Local · {repo}"
    return "local", label, repo, None


def _switch_main_tab(win, title: str) -> None:
    tw = getattr(win, "tabs", None)
    if tw is None:
        return
    for i in range(tw.count()):
        if tw.tabText(i) == title:
            tw.setCurrentIndex(i)
            return


def _flatten_history_for_api(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in messages:
        role = str(m.get("role", ""))
        content = str(m.get("content", ""))
        if role in ("system", "user", "assistant") and content.strip():
            out.append({"role": role, "content": content})
    return out


def _format_local_prompt(system: str, messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    sys = (system or "").strip()
    if sys:
        lines.append(f"(System)\n{sys}\n")
    tail = messages[-_MAX_MESSAGES_ROLL:]
    for m in tail:
        role = m.get("role", "")
        body = str(m.get("content", "")).strip()
        if not body:
            continue
        if role == "user":
            lines.append(f"User:\n{body}\n")
        elif role == "assistant":
            lines.append(f"Assistant:\n{body}\n")
    lines.append(
        "Reply as Assistant with a helpful answer. Keep formatting readable plain text "
        "(no fake JSON unless the user asked for JSON)."
    )
    return "\n".join(lines)


class _LLMChatWorker(QThread):
    chunk = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    status = pyqtSignal(str, int)

    def __init__(
        self,
        *,
        mode: str,
        settings: AppSettings,
        model_key: str,
        api_messages: list[dict[str, str]],
        local_prompt: str,
        llm_holder: dict[str, Any],
        cancel_event: threading.Event,
        max_new_tokens: int = 768,
        use_stream_api: bool = True,
    ) -> None:
        super().__init__()
        self._mode = mode
        self._settings = settings
        self._model_key = model_key
        self._api_messages = api_messages
        self._local_prompt = local_prompt
        self._holder = llm_holder
        self._cancel = cancel_event
        self._max_new = max_new_tokens
        self._stream_api = use_stream_api

    def run(self) -> None:
        if self._mode == "api":
            self._run_api()
            return
        self._run_local()

    def _run_api(self) -> None:
        try:
            client = build_openai_client_from_settings(self._settings)
            assembled: list[str] = []
            if self._stream_api:
                try:
                    for piece in client.chat_completion_stream(
                        model=self._model_key,
                        messages=self._api_messages,
                        json_mode=False,
                    ):
                        if self._cancel.is_set():
                            break
                        if piece:
                            assembled.append(piece)
                            self.chunk.emit(piece)
                    self.finished_ok.emit("".join(assembled))
                    return
                except (OpenAIRequestError, TypeError, AttributeError, ValueError):
                    pass
            user_blob = json.dumps(self._api_messages[-8:], ensure_ascii=False)
            sys0 = DEFAULT_SYSTEM_PROMPT
            for m in self._api_messages:
                if m.get("role") == "system":
                    sys0 = str(m.get("content") or sys0)
                    break
            text = client.chat_completion_text(
                model=self._model_key,
                system=sys0,
                user=user_blob,
                json_mode=False,
            )
            self.chunk.emit(text)
            self.finished_ok.emit(text)
        except OpenAIRequestError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(str(e))

    def _run_local(self) -> None:
        def on_task(task_id: str, pct: int, msg: str) -> None:
            self.status.emit(msg, pct)

        try:
            raw = _infer_text_with_optional_holder(
                self._model_key,
                self._local_prompt,
                llm_holder=self._holder,
                on_llm_task=on_task,
                max_new_tokens=self._max_new,
                inference_settings=self._settings,
                cancel_event=self._cancel,
            )
            text = (raw or "").strip()
            if self._cancel.is_set():
                self.finished_ok.emit(text + ("\n\n— Cancelled" if text else "Cancelled"))
                return
            # Local inference returns the full reply at once; streaming chunks come from the API path only.
            self.finished_ok.emit(text)
        except Exception as e:
            self.failed.emit(str(e))


class LLMChatDialog(FramelessDialog):
    """Non-modal chat window; holds local LLM in ``_llm_holder`` until teardown."""

    def __init__(self, win) -> None:
        super().__init__(win, title="LLM chat", modal=False, enable_main_blur=False)
        self._win = win
        self.setMinimumSize(520, 520)
        self._llm_holder: dict[str, Any] = {}
        self._messages: list[dict[str, str]] = []
        self._worker: _LLMChatWorker | None = None
        self._cancel_event = threading.Event()
        self._current_assist_browser: QTextBrowser | None = None

        self._subtitle = QLabel("")
        self._subtitle.setWordWrap(True)
        self._subtitle.setStyleSheet("color: #9BA6B8; font-size: 12px;")
        self.body_layout.addWidget(self._subtitle)

        self._status = QLabel("Opening…")
        self._status.setStyleSheet("color: #B7B7C2; font-size: 11px;")
        self.body_layout.addWidget(self._status)

        self._busy = QProgressBar()
        self._busy.setRange(0, 0)
        self._busy.setVisible(False)
        self.body_layout.addWidget(self._busy)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._transcript_host = QWidget()
        self._transcript_lay = QVBoxLayout(self._transcript_host)
        self._transcript_lay.setContentsMargins(0, 0, 0, 0)
        self._transcript_lay.addStretch(1)
        scroll.setWidget(self._transcript_host)
        self.body_layout.addWidget(scroll, 1)

        sys_row = QHBoxLayout()
        sys_row.addWidget(QLabel("System prompt"))
        self.body_layout.addLayout(sys_row)
        self._system_edit = QPlainTextEdit()
        self._system_edit.setPlaceholderText("Instructions for the model…")
        self._system_edit.setMaximumHeight(72)
        self.body_layout.addWidget(self._system_edit)

        self._input = _EnterSendingPlainText()
        self._input.setPlaceholderText("Message… (Enter = send, Shift+Enter = newline)")
        self._input.setMaximumHeight(100)
        self._input.send_requested.connect(self._on_send)
        self.body_layout.addWidget(self._input)

        row = QHBoxLayout()
        self._send_btn = styled_outline_button("Send", "accent_icon", min_width=72)
        self._stop_btn = styled_outline_button("Stop", "muted_icon", min_width=72)
        self._clear_btn = styled_outline_button("Clear", "muted_icon", min_width=72)
        self._model_btn = styled_outline_button("Model tab", "muted_icon", min_width=88)
        self._api_btn = styled_outline_button("API tab", "muted_icon", min_width=88)
        self._send_btn.clicked.connect(self._on_send)
        self._stop_btn.clicked.connect(self._on_stop)
        self._clear_btn.clicked.connect(self._on_clear)
        self._model_btn.clicked.connect(lambda: _switch_main_tab(self._win, "Model"))
        self._api_btn.clicked.connect(lambda: _switch_main_tab(self._win, "API"))
        row.addWidget(self._send_btn)
        row.addWidget(self._stop_btn)
        row.addWidget(self._clear_btn)
        row.addWidget(self._model_btn)
        row.addWidget(self._api_btn)
        row.addStretch(1)
        self.body_layout.addLayout(row)

        self._send_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._refresh_target()
        QTimer.singleShot(0, self._after_show_load)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        # Header matches live Model/API selection when the window is re-focused.
        self._refresh_target()

    def llm_holder_has_local_weights(self) -> bool:
        try:
            return bool(self._llm_holder.get("model") is not None)
        except Exception:
            return False

    def _after_show_load(self) -> None:
        self._status.setText("Loading conversation…")
        self._busy.setVisible(True)
        self._send_btn.setEnabled(False)
        mode, label, key, err = resolve_chat_target(self._win)
        if err:
            self._status.setText(err)
            self._subtitle.setText("")
            self._send_btn.setEnabled(False)
            self._busy.setVisible(False)
            self._system_edit.setPlainText(DEFAULT_SYSTEM_PROMPT)
            return
        self._subtitle.setText(label)
        data = load_transcript(get_paths().data_dir, mode=mode, model_key=key)
        if isinstance(data, dict):
            msgs = data.get("messages")
            if isinstance(msgs, list):
                self._messages = [
                    {"role": str(m.get("role", "")), "content": str(m.get("content", ""))}
                    for m in msgs
                    if isinstance(m, dict)
                ]
            sp = str(data.get("system_prompt") or "").strip()
            if sp:
                self._system_edit.setPlainText(sp)
            else:
                self._system_edit.setPlainText(DEFAULT_SYSTEM_PROMPT)
        else:
            self._system_edit.setPlainText(DEFAULT_SYSTEM_PROMPT)
        self._rebuild_transcript_widgets()
        self._status.setText("Ready.")
        self._busy.setVisible(False)
        self._send_btn.setEnabled(True)

    def _refresh_target(self) -> None:
        _mode, label, _key, err = resolve_chat_target(self._win)
        if err:
            self._subtitle.setText(err)
        else:
            self._subtitle.setText(label)

    def _persist(self) -> None:
        mode, _l, key, err = resolve_chat_target(self._win)
        if err or not key:
            return
        try:
            save_transcript(
                get_paths().data_dir,
                mode=mode,
                model_key=key,
                messages=self._messages,
                system_prompt=self._system_edit.toPlainText().strip() or DEFAULT_SYSTEM_PROMPT,
                max_messages=_MAX_TRANSCRIPT_PERSIST,
            )
        except Exception:
            pass

    def _rebuild_transcript_widgets(self) -> None:
        while self._transcript_lay.count() > 1:
            item = self._transcript_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for m in self._messages:
            role = m.get("role", "")
            text = str(m.get("content", ""))
            bubble = QTextBrowser()
            bubble.setOpenExternalLinks(True)
            bubble.setReadOnly(True)
            bubble.setPlainText(text)
            if role == "user":
                bubble.setStyleSheet(
                    "QTextBrowser { background: #1a1f28; color: #E8E8EE; border-radius: 8px; padding: 6px; }"
                )
            else:
                bubble.setStyleSheet(
                    "QTextBrowser { background: #12161d; color: #D8D8E0; border-radius: 8px; padding: 6px; }"
                )
            self._transcript_lay.insertWidget(self._transcript_lay.count() - 1, bubble)

    def _append_user_bubble(self, text: str) -> None:
        b = QTextBrowser()
        b.setReadOnly(True)
        b.setPlainText(text)
        b.setStyleSheet(
            "QTextBrowser { background: #1a1f28; color: #E8E8EE; border-radius: 8px; padding: 6px; }"
        )
        self._transcript_lay.insertWidget(self._transcript_lay.count() - 1, b)

    def _append_assistant_shell(self) -> QTextBrowser:
        b = QTextBrowser()
        b.setReadOnly(True)
        b.setPlainText("")
        b.setStyleSheet(
            "QTextBrowser { background: #12161d; color: #D8D8E0; border-radius: 8px; padding: 6px; }"
        )
        self._transcript_lay.insertWidget(self._transcript_lay.count() - 1, b)
        self._current_assist_browser = b
        return b

    def _scroll_end(self) -> None:
        if self._current_assist_browser:
            c = self._current_assist_browser.textCursor()
            c.movePosition(QTextCursor.MoveOperation.End)
            self._current_assist_browser.setTextCursor(c)

    def _on_send(self) -> None:
        from UI.dialogs.frameless_dialog import aquaduct_information

        mode, _label, key, err = resolve_chat_target(self._win)
        if err:
            aquaduct_information(self._win, "LLM chat", err)
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self._messages.append({"role": "user", "content": text})
        self._append_user_bubble(text)
        system = self._system_edit.toPlainText().strip() or DEFAULT_SYSTEM_PROMPT

        self._cancel_event.clear()
        self._send_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._busy.setVisible(True)
        self._status.setText("Generating…" if mode == "local" else "Streaming…")

        api_msgs: list[dict[str, str]] = [{"role": "system", "content": system}]
        api_msgs.extend(
            _flatten_history_for_api([m for m in self._messages if m.get("role") != "system"])
        )

        shell = self._append_assistant_shell()
        buf: list[str] = []

        def on_chunk(s: str) -> None:
            buf.append(s)
            shell.setPlainText("".join(buf))
            self._scroll_end()

        self._worker = _LLMChatWorker(
            mode=mode,
            settings=self._win.settings,
            model_key=key,
            api_messages=api_msgs,
            local_prompt=_format_local_prompt(system, self._messages),
            llm_holder=self._llm_holder,
            cancel_event=self._cancel_event,
        )
        self._worker.chunk.connect(on_chunk)
        self._worker.status.connect(lambda m, _p: self._status.setText(m))
        self._worker.finished_ok.connect(self._on_worker_done)
        self._worker.failed.connect(self._on_worker_fail)
        self._worker.start()

    def _on_worker_done(self, text: str) -> None:
        if self._current_assist_browser is not None:
            self._current_assist_browser.setPlainText(text)
        self._messages.append({"role": "assistant", "content": text})
        self._busy.setVisible(False)
        self._send_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status.setText("Ready.")
        self._current_assist_browser = None
        self._persist()

    def _on_worker_fail(self, msg: str) -> None:
        if self._current_assist_browser:
            self._current_assist_browser.setPlainText(f"Error: {msg}")
        self._busy.setVisible(False)
        self._send_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status.setText("Error.")
        self._current_assist_browser = None

    def _on_stop(self) -> None:
        self._cancel_event.set()
        self._status.setText("Stopping…")

    def _on_clear(self) -> None:
        self._messages.clear()
        self._rebuild_transcript_widgets()
        mode, _l, key, err = resolve_chat_target(self._win)
        if not err and key:
            try:
                delete_transcript(get_paths().data_dir, mode=mode, model_key=key)
            except Exception:
                pass
        self._persist()

    def _full_teardown(self) -> None:
        """Stop worker, unload local weights, persist transcript (plan §13)."""
        self._cancel_event.set()
        if self._worker and self._worker.isRunning():
            self._worker.wait(3000)
        if self._llm_holder.get("model") is not None:
            try:
                _dispose_causal_lm_pair(self._llm_holder.get("model"), self._llm_holder.get("tokenizer"))
            except Exception:
                pass
            self._llm_holder.clear()
        try:
            self._persist()
        except Exception:
            pass

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._full_teardown()
        try:
            fn = getattr(self._win, "_on_llm_chat_closed", None)
            if callable(fn):
                fn()
        except Exception:
            pass
        super().closeEvent(event)
