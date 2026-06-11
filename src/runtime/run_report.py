"""Per-run diagnostics: stage timings, settings fingerprint, and failure context."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.runtime.run_checkpoint import fingerprint_for_settings


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunReportSession:
    """Mutable state for the active ``run_once`` invocation."""

    def __init__(self) -> None:
        self.run_id: str = ""
        self.run_dir: Path | None = None
        self.settings: Any = None
        self.started_mono: float = 0.0
        self.started_at: str = ""
        self.stages: list[dict[str, Any]] = []
        self._open_stage: str | None = None
        self._open_started_mono: float = 0.0
        self._open_started_at: str = ""

    def begin(self, *, settings: Any, run_id: str) -> None:
        self.reset()
        self.settings = settings
        self.run_id = str(run_id or "").strip()
        self.started_mono = time.monotonic()
        self.started_at = _iso_now()

    def set_run_dir(self, run_dir: Path | None) -> None:
        self.run_dir = run_dir

    def mark_stage(self, stage: str) -> None:
        stage = str(stage or "").strip() or "(unknown)"
        now_mono = time.monotonic()
        now_iso = _iso_now()
        if self._open_stage is not None:
            elapsed = max(0.0, now_mono - self._open_started_mono)
            self.stages.append(
                {
                    "stage": self._open_stage,
                    "started_at": self._open_started_at,
                    "ended_at": now_iso,
                    "duration_s": round(elapsed, 3),
                }
            )
        self._open_stage = stage
        self._open_started_mono = now_mono
        self._open_started_at = now_iso

    def close_open_stage(self) -> None:
        if self._open_stage is None:
            return
        self.mark_stage(self._open_stage)

    def reset(self) -> None:
        self.run_id = ""
        self.run_dir = None
        self.settings = None
        self.started_mono = 0.0
        self.started_at = ""
        self.stages = []
        self._open_stage = None
        self._open_started_mono = 0.0
        self._open_started_at = ""

    def build_payload(
        self,
        *,
        status: str,
        error: BaseException | None = None,
        output_path: Path | str | None = None,
        last_stage: str = "",
    ) -> dict[str, Any]:
        self.close_open_stage()
        finished_mono = time.monotonic()
        finished_at = _iso_now()
        duration_s = round(max(0.0, finished_mono - self.started_mono), 3) if self.started_mono else 0.0
        fp = fingerprint_for_settings(self.settings) if self.settings is not None else ""
        err_block: dict[str, str] | None = None
        if error is not None:
            err_block = {
                "type": type(error).__name__,
                "message": str(error),
            }
        out_str = str(output_path).strip() if output_path is not None else ""
        return {
            "run_id": self.run_id,
            "status": str(status or "unknown"),
            "started_at": self.started_at,
            "finished_at": finished_at,
            "duration_s": duration_s,
            "fingerprint": fp,
            "last_stage": str(last_stage or "").strip() or (self.stages[-1]["stage"] if self.stages else ""),
            "output_path": out_str or None,
            "error": err_block,
            "stages": list(self.stages),
        }

    def report_path(self, *, fallback_dir: Path | None = None) -> Path | None:
        if self.run_dir is not None:
            return self.run_dir / "run_report.json"
        if fallback_dir is not None and self.run_id:
            return fallback_dir / self.run_id / "run_report.json"
        return None


_SESSION = RunReportSession()


def begin_run(*, settings: Any, run_id: str) -> None:
    _SESSION.begin(settings=settings, run_id=run_id)


def set_run_dir(run_dir: Path | None) -> None:
    _SESSION.set_run_dir(run_dir)


def mark_stage(stage: str) -> None:
    _SESSION.mark_stage(stage)


def write_report(
    *,
    status: str,
    error: BaseException | None = None,
    output_path: Path | str | None = None,
    last_stage: str = "",
    fallback_runs_dir: Path | None = None,
) -> Path | None:
    """Persist ``run_report.json`` for the active session; returns the path written or None."""
    payload = _SESSION.build_payload(
        status=status,
        error=error,
        output_path=output_path,
        last_stage=last_stage,
    )
    target = _SESSION.report_path(fallback_dir=fallback_runs_dir)
    if target is None:
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return target
    except Exception:
        return None


def reset() -> None:
    _SESSION.reset()


def settings_snapshot(settings: Any) -> dict[str, Any]:
    """Small fingerprint-friendly settings block for debugging (no secrets)."""
    if settings is None:
        return {}
    if is_dataclass(settings):
        d = asdict(settings)
    elif isinstance(settings, dict):
        d = dict(settings)
    else:
        return {"repr": repr(settings)[:500]}
    for secret_key in (
        "hf_token",
        "firecrawl_api_key",
        "elevenlabs_api_key",
        "tiktok_client_secret",
        "tiktok_access_token",
        "tiktok_refresh_token",
        "youtube_client_secret",
        "youtube_access_token",
        "youtube_refresh_token",
    ):
        if secret_key in d and d[secret_key]:
            d[secret_key] = "(redacted)"
    return d
