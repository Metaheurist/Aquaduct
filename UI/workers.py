from __future__ import annotations

import traceback

from PyQt6.QtCore import QThread, pyqtSignal

from src.config import AppSettings
from src.crawler import fetch_latest_items
from src.topic_discovery import discover_topics_from_items
from src.model_manager import download_model_to_project

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


class PipelineBatchWorker(QThread):
    progress = pyqtSignal(int, str)  # percent, status
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, settings: AppSettings, *, quantity: int):
        super().__init__()
        self.settings = settings
        self.quantity = max(1, int(quantity))

    def run(self) -> None:
        try:
            created = 0
            attempts = 0
            max_attempts = self.quantity * 3  # avoid infinite loops when no new news exists
            while created < self.quantity and attempts < max_attempts:
                attempts += 1
                self.progress.emit(
                    int((created / self.quantity) * 100),
                    f"Generating video {created + 1}/{self.quantity}…",
                )
                out = pipeline_main.run_once(settings=self.settings)
                if out is None:
                    # No new items; keep trying a bit in case another source yields something.
                    self.progress.emit(
                        int((created / self.quantity) * 100),
                        "No new items found. Trying again…",
                    )
                    continue
                created += 1
                self.progress.emit(int((created / self.quantity) * 100), f"Created {created}/{self.quantity}")

            if created == 0:
                self.done.emit("No new items found.")
            elif created < self.quantity:
                self.done.emit(f"Created {created} video(s). Ran out of new items.")
            else:
                self.done.emit(f"Created {created} video(s).")
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class TopicDiscoverWorker(QThread):
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, *, limit: int = 12):
        super().__init__()
        self.limit = limit

    def run(self) -> None:
        try:
            items = fetch_latest_items(limit=max(5, int(self.limit)))
            topics = discover_topics_from_items(items, limit=40)
            self.done.emit(topics)
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class ModelDownloadWorker(QThread):
    progress = pyqtSignal(int, str)  # percent, status
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, *, repo_ids: list[str], models_dir, title: str = "Downloading"):
        super().__init__()
        self.repo_ids = [r for r in repo_ids if r]
        self.models_dir = models_dir
        self.title = title

    def run(self) -> None:
        try:
            total_models = max(1, len(self.repo_ids))

            # TQDM bridge to Qt progress
            from tqdm.auto import tqdm
            import time

            worker = self

            class QtTqdm(tqdm):  # type: ignore[misc]
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self._last_pct = -1
                    self._last_n = -1
                    self._last_emit_t = 0.0

                def refresh(self, *args, **kwargs):  # noqa: D401
                    try:
                        def _human_bytes(x: float | int | None) -> str:
                            if x is None:
                                return "?"
                            x = float(x)
                            if x < 0:
                                return "?"
                            units = ["B", "KB", "MB", "GB", "TB"]
                            u = 0
                            while x >= 1024.0 and u < len(units) - 1:
                                x /= 1024.0
                                u += 1
                            if u == 0:
                                return f"{int(x)}{units[u]}"
                            return f"{x:.1f}{units[u]}"

                        total = getattr(self, "total", None)
                        n = getattr(self, "n", 0) or 0
                        pct = int((n / float(total)) * 100) if total else 0

                        # rate (bytes/sec) if known
                        rate = None
                        try:
                            fd = self.format_dict
                            rate = fd.get("rate", None) if isinstance(fd, dict) else None
                        except Exception:
                            rate = None

                        now = time.time()
                        should_emit = False
                        if pct != self._last_pct:
                            should_emit = True
                        # Also emit if bytes advanced, even if percent didn't change (e.g. pct stays 0 when total unknown)
                        if n != self._last_n and (now - self._last_emit_t) >= 0.35:
                            should_emit = True
                        # And emit periodically so rate updates
                        if (now - self._last_emit_t) >= 1.2:
                            should_emit = True

                        if should_emit:
                            self._last_pct = pct
                            self._last_n = n
                            self._last_emit_t = now

                            desc = str(getattr(self, "desc", "") or "Downloading…").strip()
                            n_s = _human_bytes(n)
                            total_s = _human_bytes(total) if total else "?"
                            rate_s = (_human_bytes(rate) + "/s") if rate else "?/s"
                            worker.progress.emit(pct, f"{desc}\n{n_s}/{total_s} • {rate_s}")
                    except Exception:
                        pass
                    return super().refresh(*args, **kwargs)

            for i, repo_id in enumerate(self.repo_ids, start=1):
                base = int(((i - 1) / total_models) * 100)
                self.progress.emit(base, f"[{i}/{total_models}] {repo_id}")
                download_model_to_project(repo_id, models_dir=self.models_dir, tqdm_class=QtTqdm)
                self.progress.emit(int((i / total_models) * 100), f"Downloaded: {repo_id}")

            self.done.emit("Done")
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")
