"""
Cooperative cancel / pause for long-running pipeline work (UI threads + ``main.run_once``).

Pause does not interrupt work mid-step (e.g. mid-LLM token or mid-diffusion); the run stops
or waits at the next checkpoint.
"""

from __future__ import annotations

import threading
import time


class PipelineCancelled(Exception):
    """Raised when the user stops the current run (or batch iteration)."""


class PipelineRunControl:
    """Thread-safe flags inspected from worker threads."""

    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._pause = threading.Event()  # set = paused (wait at checkpoints)

    def request_cancel(self) -> None:
        self._cancel.set()

    def request_pause(self) -> None:
        self._pause.set()

    def request_resume(self) -> None:
        self._pause.clear()

    def is_paused(self) -> bool:
        return self._pause.is_set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def checkpoint(self) -> None:
        """
        Call from the pipeline thread between expensive stages.
        Blocks while paused; raises PipelineCancelled when stopped.
        """
        while self._pause.is_set():
            if self._cancel.is_set():
                raise PipelineCancelled()
            time.sleep(0.12)
        if self._cancel.is_set():
            raise PipelineCancelled()
