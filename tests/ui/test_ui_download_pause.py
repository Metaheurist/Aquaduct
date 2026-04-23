from __future__ import annotations

from PyQt6.QtCore import QTimer

import pytest


@pytest.mark.qt
def test_download_popup_pause_saves_resume_queue(qtbot, monkeypatch):
    import UI.main_window as mw

    class DummyWorker:
        def __init__(self, *, repo_ids, models_dir, title="Downloading", remote_bytes_by_repo=None, **_kwargs):
            self.repo_ids = list(repo_ids)
            self.models_dir = models_dir
            self.title = title
            _ = remote_bytes_by_repo
            self.current_index = 0
            self.current_repo_id = ""
            self._paused = False

            # Qt signals are accessed on the real worker; provide no-ops for this test.
            class _Sig:
                def connect(self, _fn):
                    return None

            self.progress = _Sig()
            self.done = _Sig()
            self.failed = _Sig()

        def isRunning(self):
            return False

        def start(self):
            return None

        def pause(self):
            self._paused = True

        def cancel(self):
            return None

    monkeypatch.setattr(mw, "ModelDownloadWorker", DummyWorker)

    # Make popup.exec() non-blocking and auto-pause immediately.
    def _exec_and_pause(self):
        QTimer.singleShot(0, self.pause_requested.emit)
        return 0

    monkeypatch.setattr(mw.DownloadPopup, "exec", _exec_and_pause, raising=True)

    win = mw.MainWindow()
    qtbot.addWidget(win)

    win._paused_download_repo_ids = None
    win._start_download(["a/model", "b/model"], title="Downloading models")

    qtbot.waitUntil(lambda: win._paused_download_repo_ids is not None, timeout=2000)
    assert win._paused_download_repo_ids == ["a/model", "b/model"]

