from __future__ import annotations

import traceback
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.config import AppSettings
from src.crawler import fetch_latest_items, get_latest_items, get_scored_items, pick_one_item
from src.topics import effective_topic_tags, news_cache_mode_for_run, topic_tags_for_mode
from src.topic_discovery import discover_topics_from_items
from src.model_manager import (
    download_model_to_project,
    load_hf_size_cache,
    probe_hf_model,
    save_hf_size_cache,
    verify_project_model_integrity,
)

import main as pipeline_main
from src.brain import VideoPackage, generate_script
from src.characters_store import character_context_for_brain, resolve_active_character
from src.branding_video import apply_palette_to_prompts
from src.personality_auto import auto_pick_personality
from src.storyboard import build_storyboard, render_preview_grid, write_manifest
from src.utils_vram import prepare_for_next_model
from debug import dprint


def _firecrawl_kwargs(app: AppSettings) -> dict:
    return dict(
        firecrawl_enabled=bool(getattr(app, "firecrawl_enabled", False)),
        firecrawl_api_key=str(getattr(app, "firecrawl_api_key", "") or ""),
    )


def _fmt_bytes(n: int | float | None) -> str:
    if n is None:
        return "—"
    try:
        x = float(n)
    except Exception:
        return "—"
    if x < 0:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    u = 0
    while x >= 1024.0 and u < len(units) - 1:
        x /= 1024.0
        u += 1
    if u == 0:
        return f"{int(x)} {units[u]}"
    return f"{x:.1f} {units[u]}"


class PipelineWorker(QThread):
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        settings: AppSettings,
        *,
        prebuilt_pkg: VideoPackage | None = None,
        prebuilt_sources=None,
        prebuilt_prompts=None,
        prebuilt_seeds=None,
    ):
        super().__init__()
        self.settings = settings
        self.prebuilt_pkg = prebuilt_pkg
        self.prebuilt_sources = prebuilt_sources
        self.prebuilt_prompts = prebuilt_prompts
        self.prebuilt_seeds = prebuilt_seeds

    def run(self) -> None:
        try:
            dprint("workers", "PipelineWorker start", f"prebuilt={'yes' if self.prebuilt_pkg else 'no'}")
            out = pipeline_main.run_once(
                settings=self.settings,
                prebuilt_pkg=self.prebuilt_pkg,
                prebuilt_sources=self.prebuilt_sources,
                prebuilt_prompts=self.prebuilt_prompts,
                prebuilt_seeds=self.prebuilt_seeds,
            )
            if out is None:
                self.done.emit("")
            else:
                self.done.emit(str(out))
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class PipelineBatchWorker(QThread):
    # task_id, local 0–100 for that task, message (each pipeline_video run is its own 0–100)
    progress = pyqtSignal(str, int, str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, settings: AppSettings, *, quantity: int):
        super().__init__()
        self.settings = settings
        self.quantity = max(1, int(quantity))

    def run(self) -> None:
        try:
            dprint("workers", "PipelineBatchWorker start", f"quantity={self.quantity}")
            created = 0
            attempts = 0
            max_attempts = self.quantity * 3  # avoid infinite loops when no new news exists
            while created < self.quantity and attempts < max_attempts:
                attempts += 1
                n = int(self.quantity)
                self.progress.emit(
                    "pipeline_video",
                    0,
                    f"Starting video {created + 1}/{n} (attempt {attempts})…",
                )
                out = pipeline_main.run_once(settings=self.settings)
                if out is None:
                    # No new items; keep trying a bit in case another source yields something.
                    self.progress.emit(
                        "pipeline_video",
                        0,
                        "No new items — retrying…",
                    )
                    continue
                created += 1
                self.progress.emit(
                    "pipeline_video",
                    100,
                    f"Finished video {created}/{n}",
                )

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

    def __init__(self, settings: AppSettings, *, limit: int = 12, topic_mode: str = "news"):
        super().__init__()
        self.settings = settings
        self.limit = limit
        self.topic_mode = topic_mode

    def run(self) -> None:
        try:
            dprint("topics", "TopicDiscoverWorker", f"limit={self.limit}", f"mode={self.topic_mode}")
            app = self.settings
            items = fetch_latest_items(
                limit=max(5, int(self.limit)),
                topic_tags=topic_tags_for_mode(app, self.topic_mode),
                topic_mode=self.topic_mode,
                **_firecrawl_kwargs(app),
            )
            topics = discover_topics_from_items(items, limit=40)
            self.done.emit(topics)
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class FFmpegEnsureWorker(QThread):
    """
    Download static FFmpeg into ``.cache/ffmpeg`` on first use. Keeps the UI responsive
    (runs off the GUI thread).
    """

    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, ffmpeg_dir: Path):
        super().__init__()
        self.ffmpeg_dir = ffmpeg_dir

    def run(self) -> None:
        try:
            from src.utils_ffmpeg import ensure_ffmpeg, find_ffmpeg

            if find_ffmpeg(self.ffmpeg_dir):
                self.finished_ok.emit()
                return
            ensure_ffmpeg(self.ffmpeg_dir)
            self.finished_ok.emit()
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class TikTokUploadWorker(QThread):
    """Upload final.mp4 for a Tasks row to TikTok inbox (Content Posting API)."""

    finished_ok = pyqtSignal(str, str, str, float)  # message, access_token, refresh_token, expires_at_unix
    failed = pyqtSignal(str)

    def __init__(self, settings: AppSettings, task_id: str):
        super().__init__()
        self.settings = settings
        self.task_id = task_id

    def run(self) -> None:
        from pathlib import Path

        from src.tiktok_post import ensure_fresh_access_token, upload_local_video_to_inbox
        from src.upload_tasks import load_tasks, set_task_status

        try:
            tasks = load_tasks()
            t = next((x for x in tasks if x.id == self.task_id), None)
            if not t:
                self.failed.emit("Task not found")
                return
            if getattr(self.settings, "tiktok_publishing_mode", "inbox") != "inbox":
                self.failed.emit("Direct publish is not implemented — use Inbox mode in the API tab (video.upload).")
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
        except Exception as e:
            tb = traceback.format_exc()
            try:
                from src.upload_tasks import set_task_status

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
        from pathlib import Path

        from src.upload_tasks import load_tasks, set_task_status, set_youtube_upload_result
        from src.youtube_upload import (
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
                self.failed.emit("YouTube uploads are disabled — enable YouTube in the API tab.")
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
                f"Uploaded to YouTube — video id {yid} (open studio.youtube.com to manage).",
                access,
                refresh,
                exp,
            )
        except Exception as e:
            tb = traceback.format_exc()
            try:
                from src.upload_tasks import set_youtube_upload_result

                set_youtube_upload_result(self.task_id, video_id="", error=str(e))
            except Exception:
                pass
            self.failed.emit(f"{e}\n\n{tb}")


class ModelDownloadWorker(QThread):
    # task "download" — percent is 0–100 for the *current file* (per-TQDM bar)
    progress = pyqtSignal(str, int, str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        repo_ids: list[str],
        models_dir,
        title: str = "Downloading",
        remote_bytes_by_repo: dict[str, int] | None = None,
    ):
        super().__init__()
        self.repo_ids = [r for r in repo_ids if r]
        self.models_dir = models_dir
        self.title = title
        self._remote_bytes_by_repo = dict(remote_bytes_by_repo or {})
        self._stop_requested = False
        self._stop_reason: str = "cancelled"  # "cancelled" | "paused"
        self.current_index: int = 0  # 1-based index into repo_ids while running
        self.current_repo_id: str = ""

    def cancel(self) -> None:
        """
        Best-effort cancellation.
        We signal our progress bridge to abort; partial files are left in place so a later run can resume.
        """
        self._stop_requested = True
        self._stop_reason = "cancelled"

    def pause(self) -> None:
        """
        Best-effort pause.
        Same mechanics as cancel, but reported as "Paused" so UI can offer resume semantics.
        """
        self._stop_requested = True
        self._stop_reason = "paused"

    def run(self) -> None:
        try:
            dprint("workers", "ModelDownloadWorker", f"repos={len(self.repo_ids)}", str(self.repo_ids[:5]))
            total_models = max(1, len(self.repo_ids))

            # TQDM bridge to Qt progress
            from tqdm.auto import tqdm
            import time

            worker = self

            class _CancelledDownload(RuntimeError):
                pass

            class QtTqdm(tqdm):  # type: ignore[misc]
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self._last_pct = -1
                    self._last_n = -1
                    self._last_emit_t = 0.0

                def refresh(self, *args, **kwargs):  # noqa: D401
                    try:
                        if worker._stop_requested:
                            raise _CancelledDownload(worker._stop_reason)

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
                        cur_i = max(1, int(worker.current_index or 1))
                        n_r = max(1, len(worker.repo_ids))

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

                            n_s = _human_bytes(n)
                            total_s = _human_bytes(total) if total else "?"
                            rate_s = (_human_bytes(rate) + "/s") if rate else "?/s"
                            rid = str(worker.current_repo_id or "").strip() or "?"
                            msg = f"[{cur_i}/{n_r}] {rid}\n{n_s} / {total_s}  ·  {rate_s}  ·  file {pct}%"
                            worker.progress.emit("download", pct, msg)
                    except Exception:
                        pass
                    return super().refresh(*args, **kwargs)

            for i, repo_id in enumerate(self.repo_ids, start=1):
                self.current_index = int(i)
                self.current_repo_id = str(repo_id or "")

                if self._stop_requested:
                    self.done.emit("Paused" if self._stop_reason == "paused" else "Cancelled")
                    return
                base = int(((i - 1) / total_models) * 100)
                pb = self._remote_bytes_by_repo.get(str(repo_id).strip())
                ps = _fmt_bytes(pb) if pb else ""
                est = f" (~{ps})" if ps else ""
                self.progress.emit("download", 0, f"[{i}/{total_models}] {repo_id}{est}")
                try:
                    download_model_to_project(repo_id, models_dir=self.models_dir, tqdm_class=QtTqdm)
                except _CancelledDownload:
                    self.done.emit("Paused" if self._stop_reason == "paused" else "Cancelled")
                    return
                self.progress.emit("download", 100, f"Downloaded: {repo_id}")

            self.done.emit("Done")
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class ModelIntegrityVerifyWorker(QThread):
    """
    Compare local ``models/<repo>/`` files to Hugging Face Hub (per-file checksums).

    Large models can take several minutes (reads full weight files).
    """

    progress = pyqtSignal(str, str)  # repo_id, status line
    done = pyqtSignal(str)  # multiline summary for the log
    failed = pyqtSignal(str)

    def __init__(self, *, repo_ids: list[str], models_dir, scope_label: str = ""):
        super().__init__()
        self.repo_ids = [str(r).strip() for r in (repo_ids or []) if str(r).strip()]
        self.models_dir = models_dir
        self.scope_label = str(scope_label or "").strip()

    def run(self) -> None:
        try:
            lines: list[str] = []
            hdr = "Model integrity check (Hugging Face Hub checksums)"
            if self.scope_label:
                hdr += f" — {self.scope_label}"
            lines.append(hdr)

            if not self.repo_ids:
                lines.append("No repository ids to verify.")
                self.done.emit("\n".join(lines))
                return

            n = len(self.repo_ids)
            ok_n = 0
            bad_n = 0
            for i, rid in enumerate(self.repo_ids):
                self.progress.emit(rid, f"[{i + 1}/{n}] Verifying…")
                rpt = verify_project_model_integrity(rid, models_dir=Path(self.models_dir))
                lines.append(f"--- {rpt.repo_id} ---")
                if rpt.error:
                    lines.append(f"  ERROR: {rpt.error}")
                    bad_n += 1
                    continue
                if rpt.ok:
                    rev = rpt.revision or ""
                    if len(rev) > 12:
                        rev_s = f" (rev {rev[:12]}…)"
                    elif rev:
                        rev_s = f" (rev {rev})"
                    else:
                        rev_s = ""
                    lines.append(f"  OK — {rpt.checked_files} file(s) matched{rev_s}")
                    ok_n += 1
                else:
                    bad_n += 1
                    if rpt.missing_paths:
                        lines.append(f"  Missing on disk ({len(rpt.missing_paths)}): " + ", ".join(rpt.missing_paths[:8]))
                        if len(rpt.missing_paths) > 8:
                            lines.append(f"    … +{len(rpt.missing_paths) - 8} more")
                    if rpt.mismatches:
                        lines.append(f"  Hash mismatch / corruption ({len(rpt.mismatches)} file(s)):")
                        for mm in rpt.mismatches[:5]:
                            lines.append(f"    - {mm.get('path','?')} ({mm.get('algorithm','?')})")
                        if len(rpt.mismatches) > 5:
                            lines.append(f"    … +{len(rpt.mismatches) - 5} more")
                    lines.append("  Re-download this model from the Download menu if corruption is suspected.")
                if rpt.warning:
                    lines.append(f"  Note: {rpt.warning}")

            lines.append(f"Summary: {ok_n} ok, {bad_n} failed, {n} total.")
            self.done.emit("\n".join(lines))
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class ModelSizePingWorker(QThread):
    """
    On UI startup: probe each curated repo on Hugging Face (reachability + precise total size).

    Emits ``{repo_id: {"ok": bool, "bytes": int|None, "error": str}}}``.
    Old call sites merged sizes from this; we still persist successful bytes to hf_model_sizes.json.
    """

    done = pyqtSignal(dict)  # {repo_id: {"ok": bool, "bytes": int | None, "error": str}}
    failed = pyqtSignal(str)

    def __init__(self, *, repo_ids: list[str], cache_path):
        super().__init__()
        self.repo_ids = [str(r).strip() for r in (repo_ids or []) if str(r).strip()]
        self.cache_path = cache_path

    def run(self) -> None:
        try:
            merged: dict[str, int] = {}
            try:
                merged = load_hf_size_cache(self.cache_path)
            except Exception:
                merged = {}

            probe: dict[str, dict] = {}
            for rid in self.repo_ids:
                ok, b, err = probe_hf_model(rid)
                probe[str(rid)] = {
                    "ok": bool(ok),
                    "bytes": (int(b) if ok and b is not None else None),
                    "error": (err or "") if not ok else "",
                }
                if ok and b is not None:
                    merged[str(rid)] = int(b)

            try:
                save_hf_size_cache(self.cache_path, merged)
            except Exception:
                pass
            self.done.emit(probe)
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class PreviewWorker(QThread):
    # task_id, local 0–100 for that task, status text
    progress = pyqtSignal(str, int, str)
    done = pyqtSignal(object, object, object, str, str)  # pkg, sources, prompts, personality_id, confidence
    failed = pyqtSignal(str)

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings

    def run(self) -> None:
        try:
            dprint("workers", "PreviewWorker start")
            paths = pipeline_main.get_paths()
            models = pipeline_main.get_models()
            app = self.settings
            llm_id = (app.llm_model_id or "").strip() or models.llm_id

            self.progress.emit("headlines", 0, "Reading news cache…")
            fc = _firecrawl_kwargs(app)
            tags = effective_topic_tags(app)
            cm = news_cache_mode_for_run(app)
            if bool(getattr(app.video, "high_quality_topic_selection", True)):
                items = get_scored_items(paths.news_cache_dir, limit=3, topic_tags=tags, cache_mode=cm, **fc)
            else:
                items = get_latest_items(paths.news_cache_dir, limit=3, topic_tags=tags, cache_mode=cm, **fc)
            self.progress.emit("headlines", 60, "Choosing items…")
            item = pick_one_item(items)
            if not item:
                self.failed.emit("No new items found.")
                return

            sources = [{"title": it.title, "url": it.url, "source": it.source} for it in items]
            titles = [it.get("title", "") for it in sources if isinstance(it, dict)]
            self.progress.emit("headlines", 100, f"Picked {len(sources)} headline(s)")

            self.progress.emit("personality", 0, "Selecting tone…")
            picked = auto_pick_personality(
                requested_id=getattr(app, "personality_id", "auto"),
                llm_model_id=llm_id,
                titles=titles,
                topic_tags=list(tags),
            )
            self.progress.emit("personality", 100, f"{picked.preset.label}")

            active_ch = resolve_active_character(app)
            char_ctx = character_context_for_brain(active_ch) if active_ch else None

            def _llm_task(task: str, pct: int, msg: str) -> None:
                if task == "llm_load":
                    self.progress.emit("script_llm_load", pct, msg)
                elif task == "llm_generate":
                    self.progress.emit("script_llm_gen", pct, msg)

            pkg = generate_script(
                model_id=llm_id,
                items=sources,
                topic_tags=effective_topic_tags(app),
                personality_id=picked.preset.id,
                branding=getattr(app, "branding", None),
                character_context=char_ctx,
                on_llm_task=_llm_task,
            )

            prompts = [s.visual_prompt for s in pkg.segments][:10]
            prompts = apply_palette_to_prompts(prompts, getattr(app, "branding", None))

            self.progress.emit("preview", 100, "Preview ready.")
            # Minimal confidence signal: more sources = better; tag match tends to correlate with relevance.
            confidence = "High" if len(sources) >= 3 else ("Medium" if len(sources) == 2 else "Low")
            self.done.emit(pkg, sources, prompts, picked.preset.id, confidence)
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class StoryboardWorker(QThread):
    progress = pyqtSignal(str, int, str)
    done = pyqtSignal(object, object)  # manifest_path, grid_png_path
    failed = pyqtSignal(str)

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings

    def run(self) -> None:
        try:
            from pathlib import Path

            dprint("workers", "StoryboardWorker start")
            paths = pipeline_main.get_paths()
            models = pipeline_main.get_models()
            app = self.settings

            llm_id = (app.llm_model_id or "").strip() or models.llm_id
            img_id = (app.image_model_id or "").strip() or models.sdxl_turbo_id

            self.progress.emit("headlines", 0, "Reading news cache…")
            fc = _firecrawl_kwargs(app)
            tags = effective_topic_tags(app)
            cm = news_cache_mode_for_run(app)
            if bool(getattr(app.video, "high_quality_topic_selection", True)):
                items = get_scored_items(paths.news_cache_dir, limit=3, topic_tags=tags, cache_mode=cm, **fc)
            else:
                items = get_latest_items(paths.news_cache_dir, limit=3, topic_tags=tags, cache_mode=cm, **fc)
            self.progress.emit("headlines", 60, "Choosing items…")
            item = pick_one_item(items)
            if not item:
                self.failed.emit("No new items found.")
                return
            sources = [{"title": it.title, "url": it.url, "source": it.source} for it in items]
            titles = [it.get("title", "") for it in sources if isinstance(it, dict)]
            self.progress.emit("headlines", 100, f"Picked {len(sources)} headline(s)")

            self.progress.emit("personality", 0, "Selecting tone…")
            picked = auto_pick_personality(
                requested_id=getattr(app, "personality_id", "auto"),
                llm_model_id=llm_id,
                titles=titles,
                topic_tags=list(tags),
            )
            self.progress.emit("personality", 100, f"{picked.preset.label}")

            active_ch = resolve_active_character(app)
            char_ctx = character_context_for_brain(active_ch) if active_ch else None

            def _llm_task(task: str, pct: int, msg: str) -> None:
                if task == "llm_load":
                    self.progress.emit("script_llm_load", pct, msg)
                elif task == "llm_generate":
                    self.progress.emit("script_llm_gen", pct, msg)

            pkg = generate_script(
                model_id=llm_id,
                items=sources,
                topic_tags=effective_topic_tags(app),
                personality_id=picked.preset.id,
                branding=getattr(app, "branding", None),
                character_context=char_ctx,
                on_llm_task=_llm_task,
            )

            prepare_for_next_model()

            safe_dir = pipeline_main.safe_title_to_dirname(pkg.title)
            video_dir = paths.videos_dir / safe_dir
            assets_dir = video_dir / "assets"
            previews_dir = assets_dir / "previews"
            previews_dir.mkdir(parents=True, exist_ok=True)

            self.progress.emit("storyboard_build", 0, "Laying out scenes…")
            sb = build_storyboard(
                pkg,
                seed_base=getattr(app.video, "seed_base", None),
                branding=getattr(app, "branding", None),
                max_scenes=8,
                character=active_ch,
            )
            self.progress.emit("storyboard_build", 100, "Storyboard structured")

            from src.artist import generate_images

            prompts = [s.prompt for s in sb.scenes]
            seeds = [s.seed for s in sb.scenes]

            def _img_pct(pct: int, msg: str) -> None:
                self.progress.emit("storyboard_images", pct, msg)

            self.progress.emit("storyboard_images", 0, "Loading image model…")
            gen = generate_images(
                sdxl_turbo_model_id=img_id,
                prompts=prompts,
                out_dir=previews_dir,
                max_images=len(prompts),
                seeds=seeds,
                steps=4,  # quality-first preview
                on_image_progress=_img_pct,
            )
            scene_paths = [g.path for g in gen]

            # Persist manifest with preview paths
            for i, pth in enumerate(scene_paths, start=1):
                try:
                    sb.scenes[i - 1].preview_image_path  # type: ignore[attr-defined]
                except Exception:
                    pass

            manifest = assets_dir / "manifest.json"
            # write_manifest handles dataclasses; we also add preview_image_path fields
            write_manifest(
                manifest,
                storyboard=sb,
                settings={"video": dict(vars(app.video)), "models": {"llm": llm_id, "img": img_id}},
            )
            try:
                import json as _json

                m = _json.loads(manifest.read_text(encoding="utf-8"))
                for i, pth in enumerate(scene_paths, start=1):
                    if i - 1 < len(m.get("scenes", [])):
                        m["scenes"][i - 1]["preview_image_path"] = str(pth)
                        m["scenes"][i - 1]["status"] = "pending"
                manifest.write_text(_json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

            self.progress.emit("storyboard_grid", 0, "Composing grid…")
            grid = previews_dir / "grid.png"
            render_preview_grid(scene_paths=scene_paths, out_grid=grid, cols=4, thumb=256)
            self.progress.emit("storyboard_grid", 100, "Grid ready")

            self.progress.emit("storyboard", 100, "Storyboard preview ready.")
            self.done.emit(manifest, grid)
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")
