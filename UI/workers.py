from __future__ import annotations

import json
import shutil
import traceback
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.content.brain_api import expand_custom_video_instructions_openai, generate_script_openai
from src.core.config import SCRIPT_HEADLINE_FETCH_LIMIT, AppSettings
from src.runtime.model_backend import is_api_mode
from src.content.crawler import (
    fetch_article_text,
    fetch_latest_items,
    get_latest_items,
    get_scored_items,
    news_item_to_script_source,
    pick_one_item,
)
from src.content.topics import effective_topic_tags, news_cache_mode_for_run, topic_tags_for_mode
from src.content.topic_discovery import discover_topics_from_items
from src.models.model_manager import (
    download_model_to_project,
    load_hf_size_cache,
    probe_hf_model,
    save_hf_size_cache,
    verify_project_model_integrity,
)

import main as pipeline_main
from src.render.artist import generate_images
from src.content.brain import (
    VideoPackage,
    clip_article_excerpt,
    enforce_arc,
    expand_custom_video_instructions,
    generate_cast_from_storyline_llm,
    generate_script,
)
from src.content.story_context import build_script_context
from src.content.story_pipeline import run_multistage_refinement
from src.content.brain import expand_custom_field_text, generate_character_from_preset_llm
from src.core.config import get_paths
from src.content.character_presets import CharacterAutoPreset, GeneratedCharacterFields
from src.models.hf_access import ensure_hf_token_in_env, humanize_hf_hub_error
from src.models.model_integrity_cache import classify_integrity_status
from src.runtime.pipeline_control import PipelineCancelled, PipelineRunControl
from src.content.characters_store import (
    cast_to_ephemeral_character,
    character_context_for_brain,
    character_selected_in_settings,
    fallback_cast_for_show,
    resolve_character_for_pipeline,
)
from src.render.branding_video import apply_palette_to_prompts
from src.content.personality_auto import auto_pick_personality
from src.content.storyboard import build_storyboard, render_preview_grid, write_manifest
from src.util.utils_vram import prepare_for_next_model
from debug import dprint


def _expand_brief_unified(
    *,
    app: AppSettings,
    model_id: str,
    raw_instructions: str,
    video_format: str,
    personality_id: str,
    character_context: str | None,
    on_llm_task,
    try_llm_4bit: bool,
):
    if is_api_mode(app):
        return expand_custom_video_instructions_openai(
            settings=app,
            raw_instructions=raw_instructions,
            video_format=video_format,
            personality_id=personality_id,
            on_llm_task=on_llm_task,
        )
    return expand_custom_video_instructions(
        model_id=model_id,
        raw_instructions=raw_instructions,
        video_format=video_format,
        personality_id=personality_id,
        character_context=character_context,
        on_llm_task=on_llm_task,
        try_llm_4bit=try_llm_4bit,
    )


def _generate_script_unified(
    *,
    app: AppSettings,
    model_id: str,
    on_llm_task,
    try_llm_4bit: bool,
    **kw,
):
    if is_api_mode(app):
        return generate_script_openai(settings=app, on_llm_task=on_llm_task, **kw)
    return generate_script(model_id=model_id, on_llm_task=on_llm_task, try_llm_4bit=try_llm_4bit, **kw)


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
    # task_id, overall 0–100, step 0–100 (-1 unknown), message
    progress = pyqtSignal(str, int, int, str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        settings: AppSettings,
        *,
        prebuilt_pkg: VideoPackage | None = None,
        prebuilt_sources=None,
        prebuilt_prompts=None,
        prebuilt_seeds=None,
        run_control: PipelineRunControl | None = None,
    ):
        super().__init__()
        self.settings = settings
        self.prebuilt_pkg = prebuilt_pkg
        self.prebuilt_sources = prebuilt_sources
        self.prebuilt_prompts = prebuilt_prompts
        self.prebuilt_seeds = prebuilt_seeds
        self.run_control = run_control

    def run(self) -> None:
        try:
            dprint("workers", "PipelineWorker start", f"prebuilt={'yes' if self.prebuilt_pkg else 'no'}")
            out = pipeline_main.run_once(
                settings=self.settings,
                prebuilt_pkg=self.prebuilt_pkg,
                prebuilt_sources=self.prebuilt_sources,
                prebuilt_prompts=self.prebuilt_prompts,
                prebuilt_seeds=self.prebuilt_seeds,
                run_control=self.run_control,
                on_progress=lambda tid, ov, tk, msg: self.progress.emit(
                    str(tid), int(ov), int(tk), str(msg)
                ),
            )
            if out is None:
                self.done.emit("")
            else:
                self.done.emit(str(out))
        except PipelineCancelled:
            self.cancelled.emit()
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class PipelineBatchWorker(QThread):
    # task_id, overall 0–100 (batch), step 0–100 (current video pipeline), message
    progress = pyqtSignal(str, int, int, str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, settings: AppSettings, *, quantity: int, run_control: PipelineRunControl | None = None):
        super().__init__()
        self.settings = settings
        self.quantity = max(1, int(quantity))
        self.run_control = run_control

    def run(self) -> None:
        try:
            dprint("workers", "PipelineBatchWorker start", f"quantity={self.quantity}")
            created = 0
            attempts = 0
            max_attempts = self.quantity * 3  # avoid infinite loops when no new news exists
            while created < self.quantity and attempts < max_attempts:
                if self.run_control is not None and self.run_control.is_cancelled():
                    self.cancelled.emit()
                    return
                attempts += 1
                n = int(self.quantity)
                self.progress.emit(
                    "pipeline_video",
                    0,
                    -1,
                    f"Starting video {created + 1}/{n} (attempt {attempts})…",
                )
                try:
                    if self.run_control is not None:
                        self.run_control.checkpoint()

                    def on_inner(tid: str, pct: int, task_pct: int, msg: str) -> None:
                        inner = max(0, min(100, int(pct)))
                        overall = int((created * 100 + inner) / n) if n > 0 else inner
                        overall = max(0, min(100, overall))
                        tk = int(task_pct)
                        if tk < -1:
                            tk = -1
                        if tk > 100:
                            tk = 100
                        self.progress.emit(
                            "pipeline_video",
                            overall,
                            tk,
                            f"Video {created + 1}/{n}: {msg}",
                        )

                    out = pipeline_main.run_once(
                        settings=self.settings,
                        run_control=self.run_control,
                        on_progress=on_inner,
                    )
                except PipelineCancelled:
                    self.cancelled.emit()
                    return
                if out is None:
                    # No new items; keep trying a bit in case another source yields something.
                    self.progress.emit(
                        "pipeline_video",
                        0,
                        -1,
                        "No new items — retrying…",
                    )
                    continue
                created += 1
                overall_done = int((created * 100) / n) if n > 0 else 100
                self.progress.emit(
                    "pipeline_video",
                    min(100, overall_done),
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
    Download static FFmpeg into ``.Aquaduct_data/.cache/ffmpeg`` on first use. Keeps the UI responsive
    (runs off the GUI thread).
    """

    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, ffmpeg_dir: Path):
        super().__init__()
        self.ffmpeg_dir = ffmpeg_dir

    def run(self) -> None:
        try:
            from src.render.utils_ffmpeg import ensure_ffmpeg, find_ffmpeg

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

        from src.platform.tiktok_post import ensure_fresh_access_token, upload_local_video_to_inbox
        from src.platform.upload_tasks import load_tasks, set_task_status

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
        from pathlib import Path

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
                from src.platform.upload_tasks import set_youtube_upload_result

                set_youtube_upload_result(self.task_id, video_id="", error=str(e))
            except Exception:
                pass
            self.failed.emit(f"{e}\n\n{tb}")


class ModelDownloadWorker(QThread):
    # task "download" — overall 0–100 across repos; step 0–100 = current file download
    progress = pyqtSignal(str, int, int, str)
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
                            overall = int(((cur_i - 1) + (pct / 100.0)) / n_r * 100)
                            overall = max(0, min(100, overall))
                            worker.progress.emit("download", overall, pct, msg)
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
                self.progress.emit("download", base, 0, f"[{i}/{total_models}] {repo_id}{est}")
                try:
                    download_model_to_project(repo_id, models_dir=self.models_dir, tqdm_class=QtTqdm)
                except _CancelledDownload:
                    self.done.emit("Paused" if self._stop_reason == "paused" else "Cancelled")
                    return
                done_ov = int((i / total_models) * 100)
                self.progress.emit("download", min(100, done_ov), 100, f"Downloaded: {repo_id}")

            self.done.emit("Done")
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class TextExpandWorker(QThread):
    """Run ``expand_custom_field_text`` off the GUI thread (loads LLM; can take a while)."""

    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        model_id: str,
        field_label: str,
        seed: str,
        hf_token: str = "",
        hf_api_enabled: bool = True,
        try_llm_4bit: bool = True,
        app_settings: AppSettings | None = None,
    ) -> None:
        super().__init__()
        self.model_id = str(model_id or "").strip()
        self.field_label = str(field_label or "").strip()
        self.seed = str(seed or "")
        self.hf_token = str(hf_token or "").strip()
        self.hf_api_enabled = bool(hf_api_enabled)
        self.try_llm_4bit = bool(try_llm_4bit)
        self.app_settings = app_settings

    def run(self) -> None:
        try:
            if self.app_settings is not None and is_api_mode(self.app_settings):
                from src.content.brain_api import expand_custom_field_text_openai

                out = expand_custom_field_text_openai(
                    settings=self.app_settings,
                    field_label=self.field_label,
                    seed=self.seed,
                )
                self.done.emit(out)
                return
            if not self.model_id:
                self.failed.emit("No script (LLM) model selected in Model tab.")
                return
            ensure_hf_token_in_env(hf_token=self.hf_token, hf_api_enabled=self.hf_api_enabled)
            out = expand_custom_field_text(
                model_id=self.model_id,
                field_label=self.field_label,
                seed=self.seed,
                try_llm_4bit=self.try_llm_4bit,
            )
            self.done.emit(out)
        except Exception as e:
            friendly = humanize_hf_hub_error(e)
            if friendly:
                self.failed.emit(friendly)
                return
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class CharacterGenerateWorker(QThread):
    """Run ``generate_character_from_preset_llm`` off the GUI thread."""

    done = pyqtSignal(object)  # GeneratedCharacterFields
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        model_id: str,
        preset: CharacterAutoPreset,
        extra_notes: str = "",
        try_llm_4bit: bool = True,
        hf_token: str = "",
        hf_api_enabled: bool = True,
    ) -> None:
        super().__init__()
        self.model_id = str(model_id or "").strip()
        self.preset = preset
        self.extra_notes = str(extra_notes or "")
        self.try_llm_4bit = bool(try_llm_4bit)
        self.hf_token = str(hf_token or "").strip()
        self.hf_api_enabled = bool(hf_api_enabled)

    def run(self) -> None:
        try:
            if not self.model_id:
                self.failed.emit("No script (LLM) model selected in Model tab.")
                return
            ensure_hf_token_in_env(hf_token=self.hf_token, hf_api_enabled=self.hf_api_enabled)
            out = generate_character_from_preset_llm(
                model_id=self.model_id,
                preset=self.preset,
                extra_notes=self.extra_notes,
                try_llm_4bit=self.try_llm_4bit,
            )
            assert isinstance(out, GeneratedCharacterFields)
            self.done.emit(out)
        except Exception as e:
            friendly = humanize_hf_hub_error(e)
            if friendly:
                self.failed.emit(friendly)
                return
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class CharacterPortraitWorker(QThread):
    """Generate a single host portrait with the project image model; saves under data/characters/<id>/portrait.png."""

    done = pyqtSignal(str)  # reference_image_rel
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        image_model_id: str,
        character_id: str,
        visual_style: str,
        allow_nsfw: bool = False,
        steps: int = 4,
        art_style_preset_id: str = "balanced",
    ) -> None:
        super().__init__()
        self.image_model_id = str(image_model_id or "").strip()
        self.character_id = str(character_id or "").strip()
        self.visual_style = str(visual_style or "").strip()
        self.allow_nsfw = bool(allow_nsfw)
        self.steps = max(1, int(steps))
        self.art_style_preset_id = str(art_style_preset_id or "balanced").strip() or "balanced"

    def run(self) -> None:
        try:
            if not self.image_model_id:
                self.failed.emit("No image model selected on the Model tab.")
                return
            if not self.character_id:
                self.failed.emit("No character selected.")
                return
            if not self.visual_style.strip():
                self.failed.emit("Fill in Visual style before generating a portrait.")
                return

            base = get_paths().data_dir / "characters" / self.character_id
            base.mkdir(parents=True, exist_ok=True)
            tmp = base / "_gen_tmp"
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True, exist_ok=True)

            prompt = (
                f"{self.visual_style.strip()}, single character portrait, one clear subject, "
                "looking at camera, sharp focus, vertical 9:16 composition"
            )
            prepare_for_next_model()
            gen = generate_images(
                sdxl_turbo_model_id=self.image_model_id,
                prompts=[prompt],
                out_dir=tmp,
                max_images=1,
                steps=self.steps,
                allow_nsfw=self.allow_nsfw,
                art_style_preset_id=str(getattr(self, "art_style_preset_id", None) or "balanced"),
                use_style_continuity=False,
            )
            if not gen:
                self.failed.emit("Image generation returned no files.")
                return
            src = gen[0].path
            dest = base / "portrait.png"
            shutil.copy2(src, dest)
            shutil.rmtree(tmp, ignore_errors=True)
            rel = f"characters/{self.character_id}/portrait.png"
            self.done.emit(rel)
        except Exception as e:
            friendly = humanize_hf_hub_error(e)
            if friendly:
                self.failed.emit(friendly)
                return
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class ModelIntegrityVerifyWorker(QThread):
    """
    Compare local ``models/<repo>/`` files to Hugging Face Hub (per-file checksums).

    Large models can take several minutes (reads full weight files).
    """

    progress = pyqtSignal(str, str)  # repo_id, status line
    # multiline summary for the log; per-repo status for UI (ok / missing / corrupt / …)
    done = pyqtSignal(str, object)
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
                self.done.emit("\n".join(lines), {})
                return

            n = len(self.repo_ids)
            ok_n = 0
            bad_n = 0
            status_by_repo: dict[str, str] = {}
            for i, rid in enumerate(self.repo_ids):
                self.progress.emit(rid, f"[{i + 1}/{n}] Verifying…")
                rpt = verify_project_model_integrity(rid, models_dir=Path(self.models_dir))
                lines.append(f"--- {rpt.repo_id} ---")
                if rpt.error:
                    lines.append(f"  ERROR: {rpt.error}")
                    status_by_repo[str(rpt.repo_id)] = "error"
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
                    status_by_repo[str(rpt.repo_id)] = "ok"
                    ok_n += 1
                else:
                    bad_n += 1
                    status_by_repo[str(rpt.repo_id)] = classify_integrity_status(rpt)
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
            self.done.emit("\n".join(lines), status_by_repo)
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
    # task_id, overall 0–100 for that sub-task, step (-1 or same as LLM sub-progress), status text
    progress = pyqtSignal(str, int, int, str)
    done = pyqtSignal(object, object, object, str, str)  # pkg, sources, prompts, personality_id, confidence
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, settings: AppSettings, *, run_control: PipelineRunControl | None = None):
        super().__init__()
        self.settings = settings
        self.run_control = run_control

    def run(self) -> None:
        try:
            dprint("workers", "PreviewWorker start")
            if self.run_control is not None:
                self.run_control.checkpoint()
            paths = pipeline_main.get_paths()
            models = pipeline_main.get_models()
            app = self.settings
            llm_id = (app.llm_model_id or "").strip() or models.llm_id
            tags = list(effective_topic_tags(app))
            vf = str(getattr(app, "video_format", "news") or "news")
            try_llm_4bit = bool(getattr(app, "try_llm_4bit", True))

            if str(getattr(app, "run_content_mode", "preset")) == "custom":
                raw_inst = str(getattr(app, "custom_video_instructions", "") or "").strip()
                if not raw_inst:
                    self.failed.emit("No video instructions (custom mode). Enter instructions in the Run tab.")
                    return
                first_line = raw_inst.splitlines()[0].strip()[:120] or "Custom video"
                sources = [{"title": first_line, "url": "", "source": "custom"}]
                self.progress.emit("headlines", 100, -1, "Using custom instructions")
                if self.run_control is not None:
                    self.run_control.checkpoint()

                self.progress.emit("personality", 0, -1, "Selecting tone…")
                picked = auto_pick_personality(
                    requested_id=getattr(app, "personality_id", "auto"),
                    llm_model_id=llm_id,
                    titles=[first_line],
                    topic_tags=tags,
                    extra_scoring_text=raw_inst[:2000],
                )
                self.progress.emit("personality", 100, -1, f"{picked.preset.label}")
                dprint("workers", "PreviewWorker personality", picked.preset.id, picked.reason)

                active_ch = resolve_character_for_pipeline(
                    app,
                    video_format=vf,
                    topic_tags=tags,
                    headline_seed=first_line,
                )
                char_ctx = character_context_for_brain(active_ch)

                def _llm_task(task: str, pct: int, msg: str) -> None:
                    if task == "llm_load":
                        self.progress.emit("script_llm_load", pct, pct, msg)
                    elif task == "llm_generate":
                        self.progress.emit("script_llm_gen", pct, pct, msg)

                if self.run_control is not None:
                    self.run_control.checkpoint()

                expanded = _expand_brief_unified(
                    app=app,
                    model_id=llm_id,
                    raw_instructions=raw_inst,
                    video_format=vf,
                    personality_id=picked.preset.id,
                    character_context=char_ctx,
                    on_llm_task=_llm_task,
                    try_llm_4bit=try_llm_4bit,
                )
                pkg = _generate_script_unified(
                    app=app,
                    model_id=llm_id,
                    items=sources,
                    topic_tags=tags,
                    personality_id=picked.preset.id,
                    branding=getattr(app, "branding", None),
                    character_context=char_ctx,
                    creative_brief=expanded,
                    video_format=vf,
                    on_llm_task=_llm_task,
                    try_llm_4bit=try_llm_4bit,
                )
                pkg = enforce_arc(pkg, video_format=vf)
            else:
                cm = news_cache_mode_for_run(app)
                self.progress.emit(
                    "headlines",
                    0,
                    -1,
                    "Fetching headlines…" if cm == "unhinged" else "Reading news cache…",
                )
                fc = _firecrawl_kwargs(app)
                if cm == "unhinged":
                    if bool(getattr(app.video, "high_quality_topic_selection", True)):
                        items = get_scored_items(
                            paths.news_cache_dir,
                            limit=SCRIPT_HEADLINE_FETCH_LIMIT,
                            topic_tags=tags,
                            cache_mode=cm,
                            persist_cache=False,
                            **fc,
                        )
                    else:
                        items = fetch_latest_items(limit=SCRIPT_HEADLINE_FETCH_LIMIT, topic_tags=tags, topic_mode=cm, **fc)
                elif bool(getattr(app.video, "high_quality_topic_selection", True)):
                    items = get_scored_items(paths.news_cache_dir, limit=SCRIPT_HEADLINE_FETCH_LIMIT, topic_tags=tags, cache_mode=cm, **fc)
                else:
                    items = get_latest_items(paths.news_cache_dir, limit=SCRIPT_HEADLINE_FETCH_LIMIT, topic_tags=tags, cache_mode=cm, **fc)
                self.progress.emit("headlines", 60, -1, "Choosing items…")
                item = pick_one_item(items)
                if not item:
                    self.failed.emit("No new items found.")
                    return

                sources = [news_item_to_script_source(it) for it in items]
                titles = [it.get("title", "") for it in sources if isinstance(it, dict)]
                self.progress.emit("headlines", 100, -1, f"Picked {len(sources)} headline(s)")

                if self.run_control is not None:
                    self.run_control.checkpoint()

                self.progress.emit("personality", 0, -1, "Selecting tone…")
                picked = auto_pick_personality(
                    requested_id=getattr(app, "personality_id", "auto"),
                    llm_model_id=llm_id,
                    titles=titles,
                    topic_tags=tags,
                    extra_scoring_text="",
                )
                self.progress.emit("personality", 100, -1, f"{picked.preset.label}")
                dprint("workers", "PreviewWorker personality", picked.preset.id, picked.reason)

                active_ch = resolve_character_for_pipeline(
                    app,
                    video_format=vf,
                    topic_tags=tags,
                    headline_seed=str(sources[0].get("title") or "") if sources else "",
                )
                char_ctx = character_context_for_brain(active_ch)

                def _llm_task(task: str, pct: int, msg: str) -> None:
                    if task == "llm_load":
                        self.progress.emit("script_llm_load", pct, pct, msg)
                    elif task == "llm_generate":
                        self.progress.emit("script_llm_gen", pct, pct, msg)

                if self.run_control is not None:
                    self.run_control.checkpoint()

                article_excerpt = ""
                if bool(getattr(app.video, "fetch_article_text", True)) and item is not None:
                    try:
                        article_excerpt = clip_article_excerpt(
                            fetch_article_text(str(getattr(item, "url", "") or ""), **_firecrawl_kwargs(app))
                        )
                    except Exception:
                        article_excerpt = ""

                pkg = _generate_script_unified(
                    app=app,
                    model_id=llm_id,
                    items=sources,
                    topic_tags=tags,
                    personality_id=picked.preset.id,
                    branding=getattr(app, "branding", None),
                    character_context=char_ctx,
                    video_format=vf,
                    on_llm_task=_llm_task,
                    try_llm_4bit=try_llm_4bit,
                    article_excerpt=article_excerpt,
                )
                pkg = enforce_arc(pkg, video_format=vf)

            prompts = [s.visual_prompt for s in pkg.segments][:18]
            prompts = apply_palette_to_prompts(prompts, getattr(app, "branding", None))

            self.progress.emit("preview", 100, -1, "Preview ready.")
            # Minimal confidence signal: more sources = better; tag match tends to correlate with relevance.
            confidence = "High" if len(sources) >= 5 else ("Medium" if len(sources) >= 2 else "Low")
            self.done.emit(pkg, sources, prompts, picked.preset.id, confidence)
        except PipelineCancelled:
            self.cancelled.emit()
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class StoryboardWorker(QThread):
    progress = pyqtSignal(str, int, int, str)
    done = pyqtSignal(object, object)  # manifest_path, grid_png_path
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, settings: AppSettings, *, run_control: PipelineRunControl | None = None):
        super().__init__()
        self.settings = settings
        self.run_control = run_control

    def run(self) -> None:
        try:
            from pathlib import Path

            dprint("workers", "StoryboardWorker start")
            if self.run_control is not None:
                self.run_control.checkpoint()
            paths = pipeline_main.get_paths()
            models = pipeline_main.get_models()
            app = self.settings
            diffusion_ref_path: Path | None = None
            generated_cast: list[dict] | None = None

            llm_id = (app.llm_model_id or "").strip() or models.llm_id
            img_id = (app.image_model_id or "").strip() or models.sdxl_turbo_id
            tags = list(effective_topic_tags(app))
            vf = str(getattr(app, "video_format", "news") or "news")
            try_llm_4bit = bool(getattr(app, "try_llm_4bit", True))

            if str(getattr(app, "run_content_mode", "preset")) == "custom":
                raw_inst = str(getattr(app, "custom_video_instructions", "") or "").strip()
                if not raw_inst:
                    self.failed.emit("No video instructions (custom mode). Enter instructions in the Run tab.")
                    return
                first_line = raw_inst.splitlines()[0].strip()[:120] or "Custom video"
                sources = [{"title": first_line, "url": "", "source": "custom"}]
                self.progress.emit("headlines", 100, -1, "Using custom instructions")
                if self.run_control is not None:
                    self.run_control.checkpoint()

                self.progress.emit("personality", 0, -1, "Selecting tone…")
                picked = auto_pick_personality(
                    requested_id=getattr(app, "personality_id", "auto"),
                    llm_model_id=llm_id,
                    titles=[first_line],
                    topic_tags=tags,
                    extra_scoring_text=raw_inst[:2000],
                )
                self.progress.emit("personality", 100, -1, f"{picked.preset.label}")
                dprint("workers", "StoryboardWorker personality", picked.preset.id, picked.reason)

                active_ch = resolve_character_for_pipeline(
                    app,
                    video_format=vf,
                    topic_tags=tags,
                    headline_seed=first_line,
                )
                char_ctx = character_context_for_brain(active_ch)

                def _llm_task(task: str, pct: int, msg: str) -> None:
                    if task == "llm_load":
                        self.progress.emit("script_llm_load", pct, pct, msg)
                    elif task == "llm_generate":
                        self.progress.emit("script_llm_gen", pct, pct, msg)

                if self.run_control is not None:
                    self.run_control.checkpoint()

                script_digest = ""
                script_ref_notes = ""
                if bool(getattr(app.video, "story_web_context", False)) or bool(
                    getattr(app.video, "story_reference_images", False)
                ):
                    ctx_dir = paths.cache_dir / "storyboard_script_context"
                    ctx_dir.mkdir(parents=True, exist_ok=True)
                    script_digest, _, diffusion_ref_path, script_ref_notes = build_script_context(
                        topic_tags=tags,
                        source_titles=[first_line],
                        stored_firecrawl_key=str(getattr(app, "firecrawl_api_key", "") or ""),
                        firecrawl_enabled=bool(getattr(app, "firecrawl_enabled", False)),
                        want_web=bool(getattr(app.video, "story_web_context", False)),
                        want_refs=bool(getattr(app.video, "story_reference_images", False)),
                        out_dir=ctx_dir,
                        extra_markdown=raw_inst[:8000],
                    )

                expanded = _expand_brief_unified(
                    app=app,
                    model_id=llm_id,
                    raw_instructions=raw_inst,
                    video_format=vf,
                    personality_id=picked.preset.id,
                    character_context=char_ctx,
                    on_llm_task=_llm_task,
                    try_llm_4bit=try_llm_4bit,
                )
                pkg = _generate_script_unified(
                    app=app,
                    model_id=llm_id,
                    items=sources,
                    topic_tags=tags,
                    personality_id=picked.preset.id,
                    branding=getattr(app, "branding", None),
                    character_context=char_ctx,
                    creative_brief=expanded,
                    video_format=vf,
                    on_llm_task=_llm_task,
                    try_llm_4bit=try_llm_4bit,
                    supplement_context=script_digest,
                )
                pkg = enforce_arc(pkg, video_format=vf)
                if bool(getattr(app.video, "story_multistage_enabled", False)) and not is_api_mode(app):

                    def _ms_sb(task: str, pct: int, msg: str) -> None:
                        if task == "llm_load":
                            self.progress.emit("script_llm_load", pct, pct, msg)
                        elif task == "llm_generate":
                            self.progress.emit("script_llm_gen", pct, pct, msg)

                    pkg = run_multistage_refinement(
                        pkg,
                        video_format=vf,
                        model_id=llm_id,
                        web_digest=script_digest,
                        reference_notes=script_ref_notes,
                        try_llm_4bit=try_llm_4bit,
                        on_llm_task=_ms_sb,
                    )
                if not character_selected_in_settings(app):
                    if is_api_mode(app):
                        try:
                            generated_cast = fallback_cast_for_show(
                                video_format=vf, topic_tags=tags, headline_seed=str(pkg.title or "")
                            )
                            active_ch = cast_to_ephemeral_character(cast=generated_cast, video_format=vf)
                            char_ctx = character_context_for_brain(active_ch)
                        except Exception:
                            pass
                    else:
                        try:
                            cast = generate_cast_from_storyline_llm(
                                model_id=llm_id,
                                video_format=vf,
                                storyline_title=str(pkg.title or ""),
                                storyline_text=pkg.narration_text(),
                                topic_tags=tags,
                                on_llm_task=_llm_task,
                                try_llm_4bit=try_llm_4bit,
                            )
                            generated_cast = cast
                            active_ch = cast_to_ephemeral_character(cast=cast, video_format=vf)
                            char_ctx = character_context_for_brain(active_ch)
                        except Exception:
                            try:
                                generated_cast = fallback_cast_for_show(
                                    video_format=vf, topic_tags=tags, headline_seed=str(pkg.title or "")
                                )
                                active_ch = cast_to_ephemeral_character(cast=generated_cast, video_format=vf)
                                char_ctx = character_context_for_brain(active_ch)
                            except Exception:
                                pass
                            pass
            else:
                cm = news_cache_mode_for_run(app)
                self.progress.emit(
                    "headlines",
                    0,
                    -1,
                    "Fetching headlines…" if cm == "unhinged" else "Reading news cache…",
                )
                fc = _firecrawl_kwargs(app)
                if cm == "unhinged":
                    if bool(getattr(app.video, "high_quality_topic_selection", True)):
                        items = get_scored_items(
                            paths.news_cache_dir,
                            limit=SCRIPT_HEADLINE_FETCH_LIMIT,
                            topic_tags=tags,
                            cache_mode=cm,
                            persist_cache=False,
                            **fc,
                        )
                    else:
                        items = fetch_latest_items(limit=SCRIPT_HEADLINE_FETCH_LIMIT, topic_tags=tags, topic_mode=cm, **fc)
                elif bool(getattr(app.video, "high_quality_topic_selection", True)):
                    items = get_scored_items(paths.news_cache_dir, limit=SCRIPT_HEADLINE_FETCH_LIMIT, topic_tags=tags, cache_mode=cm, **fc)
                else:
                    items = get_latest_items(paths.news_cache_dir, limit=SCRIPT_HEADLINE_FETCH_LIMIT, topic_tags=tags, cache_mode=cm, **fc)
                self.progress.emit("headlines", 60, -1, "Choosing items…")
                item = pick_one_item(items)
                if not item:
                    self.failed.emit("No new items found.")
                    return
                sources = [news_item_to_script_source(it) for it in items]
                titles = [it.get("title", "") for it in sources if isinstance(it, dict)]
                self.progress.emit("headlines", 100, -1, f"Picked {len(sources)} headline(s)")

                if self.run_control is not None:
                    self.run_control.checkpoint()

                self.progress.emit("personality", 0, -1, "Selecting tone…")
                picked = auto_pick_personality(
                    requested_id=getattr(app, "personality_id", "auto"),
                    llm_model_id=llm_id,
                    titles=titles,
                    topic_tags=tags,
                    extra_scoring_text="",
                )
                self.progress.emit("personality", 100, -1, f"{picked.preset.label}")
                dprint("workers", "StoryboardWorker personality", picked.preset.id, picked.reason)

                active_ch = resolve_character_for_pipeline(
                    app,
                    video_format=vf,
                    topic_tags=tags,
                    headline_seed=str(sources[0].get("title") or "") if sources else "",
                )
                char_ctx = character_context_for_brain(active_ch)

                def _llm_task(task: str, pct: int, msg: str) -> None:
                    if task == "llm_load":
                        self.progress.emit("script_llm_load", pct, pct, msg)
                    elif task == "llm_generate":
                        self.progress.emit("script_llm_gen", pct, pct, msg)

                if self.run_control is not None:
                    self.run_control.checkpoint()

                article_excerpt = ""
                if bool(getattr(app.video, "fetch_article_text", True)) and item is not None:
                    try:
                        article_excerpt = clip_article_excerpt(
                            fetch_article_text(str(getattr(item, "url", "") or ""), **_firecrawl_kwargs(app))
                        )
                    except Exception:
                        article_excerpt = ""

                script_digest = ""
                script_ref_notes = ""
                if bool(getattr(app.video, "story_web_context", False)) or bool(
                    getattr(app.video, "story_reference_images", False)
                ):
                    ctx_dir = paths.cache_dir / "storyboard_script_context"
                    ctx_dir.mkdir(parents=True, exist_ok=True)
                    script_digest, _, diffusion_ref_path, script_ref_notes = build_script_context(
                        topic_tags=tags,
                        source_titles=titles,
                        stored_firecrawl_key=str(getattr(app, "firecrawl_api_key", "") or ""),
                        firecrawl_enabled=bool(getattr(app, "firecrawl_enabled", False)),
                        want_web=bool(getattr(app.video, "story_web_context", False)),
                        want_refs=bool(getattr(app.video, "story_reference_images", False)),
                        out_dir=ctx_dir,
                        extra_markdown=(article_excerpt or "")[:12000],
                    )

                pkg = _generate_script_unified(
                    app=app,
                    model_id=llm_id,
                    items=sources,
                    topic_tags=tags,
                    personality_id=picked.preset.id,
                    branding=getattr(app, "branding", None),
                    character_context=char_ctx,
                    video_format=vf,
                    on_llm_task=_llm_task,
                    try_llm_4bit=try_llm_4bit,
                    article_excerpt=article_excerpt,
                    supplement_context=script_digest,
                )
                pkg = enforce_arc(pkg, video_format=vf)
                if bool(getattr(app.video, "story_multistage_enabled", False)) and not is_api_mode(app):

                    def _ms2(task: str, pct: int, msg: str) -> None:
                        if task == "llm_load":
                            self.progress.emit("script_llm_load", pct, pct, msg)
                        elif task == "llm_generate":
                            self.progress.emit("script_llm_gen", pct, pct, msg)

                    pkg = run_multistage_refinement(
                        pkg,
                        video_format=vf,
                        model_id=llm_id,
                        web_digest=script_digest,
                        reference_notes=script_ref_notes,
                        try_llm_4bit=try_llm_4bit,
                        on_llm_task=_ms2,
                    )
                if not character_selected_in_settings(app):
                    if is_api_mode(app):
                        try:
                            generated_cast = fallback_cast_for_show(
                                video_format=vf,
                                topic_tags=tags,
                                headline_seed=str(sources[0].get("title") or "") if sources else "",
                            )
                            active_ch = cast_to_ephemeral_character(cast=generated_cast, video_format=vf)
                            char_ctx = character_context_for_brain(active_ch)
                        except Exception:
                            pass
                    else:
                        try:
                            cast2 = generate_cast_from_storyline_llm(
                                model_id=llm_id,
                                video_format=vf,
                                storyline_title=str(pkg.title or ""),
                                storyline_text=pkg.narration_text(),
                                topic_tags=tags,
                                on_llm_task=_llm_task,
                                try_llm_4bit=try_llm_4bit,
                            )
                            generated_cast = cast2
                            active_ch = cast_to_ephemeral_character(cast=cast2, video_format=vf)
                            char_ctx = character_context_for_brain(active_ch)
                        except Exception:
                            try:
                                generated_cast = fallback_cast_for_show(
                                    video_format=vf,
                                    topic_tags=tags,
                                    headline_seed=str(sources[0].get("title") or "") if sources else "",
                                )
                                active_ch = cast_to_ephemeral_character(cast=generated_cast, video_format=vf)
                                char_ctx = character_context_for_brain(active_ch)
                            except Exception:
                                pass

            prepare_for_next_model()

            safe_dir = pipeline_main.safe_title_to_dirname(pkg.title)
            video_dir = paths.videos_dir / safe_dir
            assets_dir = video_dir / "assets"
            if not character_selected_in_settings(app):
                try:
                    assets_dir.mkdir(parents=True, exist_ok=True)
                    cast_path = assets_dir / "generated_cast.json"
                    if generated_cast is not None:
                        cast_path.write_text(
                            json.dumps({"video_format": vf, "characters": generated_cast}, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                    else:
                        cast_path.write_text(
                            json.dumps(
                                {"video_format": vf, "character_context": character_context_for_brain(active_ch)},
                                indent=2,
                                ensure_ascii=False,
                            ),
                            encoding="utf-8",
                        )
                except Exception:
                    pass
            previews_dir = assets_dir / "previews"
            previews_dir.mkdir(parents=True, exist_ok=True)

            self.progress.emit("storyboard_build", 0, -1, "Laying out scenes…")
            sb = build_storyboard(
                pkg,
                seed_base=getattr(app.video, "seed_base", None),
                branding=getattr(app, "branding", None),
                max_scenes=8,
                character=active_ch,
            )
            self.progress.emit("storyboard_build", 100, -1, "Storyboard structured")

            from src.render.artist import generate_images

            prompts = [s.prompt for s in sb.scenes]
            seeds = [s.seed for s in sb.scenes]

            def _img_pct(pct: int, msg: str) -> None:
                self.progress.emit("storyboard_images", pct, pct, msg)

            if self.run_control is not None:
                self.run_control.checkpoint()

            self.progress.emit("storyboard_images", 0, -1, "Loading image model…" if not is_api_mode(app) else "API images…")
            _ref_kw: dict = {}
            if (
                diffusion_ref_path is not None
                and diffusion_ref_path.exists()
                and bool(getattr(app.video, "story_reference_images", False))
            ):
                _ref_kw = {
                    "external_reference_image": diffusion_ref_path,
                    "external_reference_strength": 0.55,
                }
            if is_api_mode(app):
                from src.runtime.api_generation import generate_still_png_bytes

                scene_paths = []
                for i, pr in enumerate(prompts):
                    _img_pct(int(100 * i / max(len(prompts), 1)), f"API still {i + 1}/{len(prompts)}…")
                    data = generate_still_png_bytes(settings=app, prompt=str(pr or ""))
                    pth = previews_dir / f"prev_{i + 1:02d}.png"
                    pth.write_bytes(data)
                    scene_paths.append(pth)
            else:
                gen = generate_images(
                    sdxl_turbo_model_id=img_id,
                    prompts=prompts,
                    out_dir=previews_dir,
                    max_images=len(prompts),
                    seeds=seeds,
                    steps=4,  # quality-first preview
                    allow_nsfw=bool(getattr(app, "allow_nsfw", False)),
                    on_image_progress=_img_pct,
                    art_style_preset_id=str(getattr(app, "art_style_preset_id", None) or "balanced"),
                    **_ref_kw,
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

            self.progress.emit("storyboard_grid", 0, -1, "Composing grid…")
            grid = previews_dir / "grid.png"
            render_preview_grid(scene_paths=scene_paths, out_grid=grid, cols=4, thumb=256)
            self.progress.emit("storyboard_grid", 100, -1, "Grid ready")

            self.progress.emit("storyboard", 100, -1, "Storyboard preview ready.")
            self.done.emit(manifest, grid)
        except PipelineCancelled:
            self.cancelled.emit()
        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")
