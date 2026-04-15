from __future__ import annotations

import traceback

from PyQt6.QtCore import QThread, pyqtSignal

from src.config import AppSettings

import main as pipeline_main


class PipelineWorker(QThread):
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings

    def run(self) -> None:
        try:
            out = pipeline_main.run_once(settings=self.settings)
            if out is None:
                self.done.emit("")
            else:
                self.done.emit(str(out))
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")
