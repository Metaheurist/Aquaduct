from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from src.core.config import get_paths

UploadTaskStatus = Literal["pending", "approved", "posted", "failed"]


def upload_tasks_path() -> Path:
    return get_paths().data_dir / "upload_tasks.json"


@dataclass
class UploadTask:
    """One finished render queued for review / TikTok upload."""

    id: str
    video_dir: str  # absolute path to folder containing final.mp4
    title: str
    created_at: str  # ISO 8601 UTC
    status: UploadTaskStatus = "pending"
    upload_error: str = ""
    youtube_video_id: str = ""
    youtube_status: str = ""  # posted | failed | ""
    youtube_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "video_dir": self.video_dir,
            "title": self.title,
            "created_at": self.created_at,
            "status": self.status,
            "upload_error": self.upload_error,
            "youtube_video_id": self.youtube_video_id,
            "youtube_status": self.youtube_status,
            "youtube_error": self.youtube_error,
        }

    @staticmethod
    def from_dict(d: Any) -> UploadTask | None:
        if not isinstance(d, dict):
            return None
        try:
            vid = str(d.get("video_dir", "")).strip()
            if not vid:
                return None
            st = str(d.get("status", "pending"))
            if st not in ("pending", "approved", "posted", "failed"):
                st = "pending"
            return UploadTask(
                id=str(d.get("id") or uuid.uuid4().hex),
                video_dir=str(Path(vid).resolve()),
                title=str(d.get("title", "")).strip() or Path(vid).name,
                created_at=str(d.get("created_at", "")).strip()
                or datetime.now(timezone.utc).isoformat(),
                status=st,  # type: ignore[arg-type]
                upload_error=str(d.get("upload_error", "") or ""),
                youtube_video_id=str(d.get("youtube_video_id", "") or ""),
                youtube_status=str(d.get("youtube_status", "") or ""),
                youtube_error=str(d.get("youtube_error", "") or ""),
            )
        except Exception:
            return None


def load_tasks() -> list[UploadTask]:
    p = upload_tasks_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out: list[UploadTask] = []
    for item in raw:
        t = UploadTask.from_dict(item)
        if t is not None:
            out.append(t)
    return out


def save_tasks(tasks: list[UploadTask]) -> None:
    p = upload_tasks_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = [t.to_dict() for t in tasks]
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_title_from_video_dir(video_dir: Path) -> str:
    meta = video_dir / "meta.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                t = data.get("title")
                if isinstance(t, str) and t.strip():
                    return t.strip()[:200]
        except Exception:
            pass
    return video_dir.name[:200]


def append_task_for_video_dir(video_dir: Path) -> UploadTask | None:
    """Append a task if `video_dir` has final.mp4 and is not already in the list."""
    video_dir = video_dir.resolve()
    final_mp4 = video_dir / "final.mp4"
    if not final_mp4.is_file():
        return None
    key = str(video_dir)
    tasks = load_tasks()
    existing = {str(Path(t.video_dir).resolve()) for t in tasks}
    if key in existing:
        return None
    task = UploadTask(
        id=uuid.uuid4().hex,
        video_dir=key,
        title=_read_title_from_video_dir(video_dir),
        created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        status="pending",
    )
    tasks.insert(0, task)
    # cap list size
    save_tasks(tasks[:500])
    return task


def set_task_status(task_id: str, status: UploadTaskStatus, upload_error: str = "") -> None:
    tasks = load_tasks()
    for i, t in enumerate(tasks):
        if t.id != task_id:
            continue
        tasks[i] = replace(t, status=status, upload_error=upload_error)
        save_tasks(tasks)
        return


def set_youtube_upload_result(task_id: str, *, video_id: str = "", error: str = "") -> None:
    tasks = load_tasks()
    for i, t in enumerate(tasks):
        if t.id != task_id:
            continue
        y_status = "posted" if video_id and not error else ("failed" if error else "")
        tasks[i] = replace(
            t,
            youtube_video_id=str(video_id or ""),
            youtube_status=y_status,
            youtube_error=str(error or ""),
        )
        save_tasks(tasks)
        return


def remove_task(task_id: str) -> None:
    tasks = [t for t in load_tasks() if t.id != task_id]
    save_tasks(tasks)
