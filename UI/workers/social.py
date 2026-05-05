from __future__ import annotations

import traceback
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import AppSettings

from UI.workers.common import _reraise_system_interrupt


class TikTokUploadWorker(QThread):
    """Upload final.mp4 for a Tasks row to TikTok inbox (Content Posting API)."""

    finished_ok = pyqtSignal(str, str, str, float)  # message, access_token, refresh_token, expires_at_unix
    failed = pyqtSignal(str)

    def __init__(self, settings: AppSettings, task_id: str):
        super().__init__()
        self.settings = settings
        self.task_id = task_id

    def run(self) -> None:
        from src.platform.tiktok_post import ensure_fresh_access_token, upload_local_video_to_inbox
        from src.platform.upload_tasks import load_tasks, set_task_status

        try:
            tasks = load_tasks()
            t = next((x for x in tasks if x.id == self.task_id), None)
            if not t:
                self.failed.emit("Task not found")
                return
            if getattr(self.settings, "tiktok_publishing_mode", "inbox") != "inbox":
                self.failed.emit("Direct publish is not implemented - use Inbox mode in the API tab (video.upload).")
                return
            s = self.settings
            access, refresh, exp = ensure_fresh_access_token(
                str(s.tiktok_client_key),
                str(s.tiktok_client_secret),
                str(s.tiktok_access_token or ""),
                str(s.tiktok_refresh_token or ""),
                float(s.tiktok_token_expires_at or 0),
            )
            vid = Path(t.video_dir) / "final.mp4"
            _pid, msg = upload_local_video_to_inbox(access, vid)
            set_task_status(self.task_id, "posted", "")
            self.finished_ok.emit(msg, access, refresh, exp)
        except BaseException as e:
            _reraise_system_interrupt(e)
            tb = traceback.format_exc()
            try:
                from src.platform.upload_tasks import set_task_status

                set_task_status(self.task_id, "failed", str(e))
            except Exception:
                pass
            self.failed.emit(f"{e}\n\n{tb}")


class YouTubeUploadWorker(QThread):
    """Upload final.mp4 for a Tasks row via YouTube Data API (resumable upload)."""

    finished_ok = pyqtSignal(str, str, str, float)  # message, access_token, refresh_token, expires_at_unix
    failed = pyqtSignal(str)

    def __init__(self, settings: AppSettings, task_id: str):
        super().__init__()
        self.settings = settings
        self.task_id = task_id

    def run(self) -> None:
        from src.platform.upload_tasks import load_tasks, set_task_status, set_youtube_upload_result
        from src.platform.youtube_upload import (
            build_shorts_title_description,
            ensure_youtube_access_token,
            upload_mp4_resumable,
        )

        try:
            tasks = load_tasks()
            t = next((x for x in tasks if x.id == self.task_id), None)
            if not t:
                self.failed.emit("Task not found")
                return
            s = self.settings
            if not bool(getattr(s, "youtube_enabled", False)):
                self.failed.emit("YouTube uploads are disabled - enable YouTube in the API tab.")
                return
            access, refresh, exp = ensure_youtube_access_token(
                str(s.youtube_client_id or ""),
                str(s.youtube_client_secret or ""),
                str(s.youtube_access_token or ""),
                str(s.youtube_refresh_token or ""),
                float(s.youtube_token_expires_at or 0),
            )
            vid_path = Path(t.video_dir) / "final.mp4"
            title, desc = build_shorts_title_description(
                Path(t.video_dir),
                add_shorts_hashtag=bool(getattr(s, "youtube_add_shorts_hashtag", True)),
            )
            priv = str(getattr(s, "youtube_privacy_status", "private") or "private")
            if priv not in ("public", "unlisted", "private"):
                priv = "private"
            yid = upload_mp4_resumable(
                access,
                vid_path,
                title=title,
                description=desc,
                privacy_status=priv,
            )
            set_youtube_upload_result(self.task_id, video_id=yid, error="")
            set_task_status(self.task_id, "posted", "")
            self.finished_ok.emit(
                f"Uploaded to YouTube - video id {yid} (open studio.youtube.com to manage).",
                access,
                refresh,
                exp,
            )
        except BaseException as e:
            _reraise_system_interrupt(e)
            tb = traceback.format_exc()
            try:
                from src.platform.upload_tasks import set_youtube_upload_result

                set_youtube_upload_result(self.task_id, video_id="", error=str(e))
            except Exception:
                pass
            self.failed.emit(f"{e}\n\n{tb}")
