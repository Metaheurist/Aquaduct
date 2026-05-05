from __future__ import annotations

import json
import shutil
import traceback
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import SCRIPT_HEADLINE_FETCH_LIMIT, AppSettings, get_models, get_paths, media_output_root, safe_title_to_dirname
from src.series.context import SeriesContext
from src.runtime.api_generation import generate_still_png_bytes
from src.runtime.model_backend import is_api_mode
from src.content.crawler import (
    fetch_article_text,
    fetch_latest_items,
    get_latest_items,
    get_scored_items,
    news_item_to_script_source,
    pick_one_item,
)
from src.content.topics import (
    effective_topic_tags,
    news_cache_mode_for_run,
    video_format_skips_seen_url_disk_cache,
)
from src.content.topic_research_assets import topic_research_digest_for_script
from src.runtime.pipeline_api import run_once as pipeline_run_once
from src.render.artist import generate_images
from src.content.brain import (
    VideoPackage,
    clip_article_excerpt,
    enforce_arc,
    generate_cast_from_storyline_llm,
)
from src.content.story_context import build_script_context
from src.content.story_pipeline import run_multistage_refinement
from src.runtime.pipeline_control import PipelineCancelled, PipelineRunControl
from src.runtime.pipeline_notice import pipeline_notice_scope
from src.runtime.oom_retry import QuantDowngradeExhaustedError
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
from src.util.cuda_device_policy import resolve_diffusion_cuda_device_index, resolve_llm_cuda_device_index
from src.util.memory_budget import release_between_stages

from UI.workers.common import (
    _expand_brief_unified,
    _failure_text_with_cuda_hints,
    _firecrawl_kwargs,
    _generate_script_unified,
    _reraise_system_interrupt,
)
from debug import dprint


class PipelineWorker(QThread):
    # task_id, overall 0–100, step 0–100 (-1 unknown), message
    progress = pyqtSignal(str, int, int, str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)
    #: Non-fatal notices during ``run_once`` (VRAM warnings, etc.) - shown as UI dialogs from main thread.
    pipeline_warning = pyqtSignal(str, str)
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
        series_context: SeriesContext | None = None,
    ):
        super().__init__()
        self.settings = settings
        self.prebuilt_pkg = prebuilt_pkg
        self.prebuilt_sources = prebuilt_sources
        self.prebuilt_prompts = prebuilt_prompts
        self.prebuilt_seeds = prebuilt_seeds
        self.run_control = run_control
        self.series_context = series_context

    def run(self) -> None:
        try:
            dprint("workers", "PipelineWorker start", f"prebuilt={'yes' if self.prebuilt_pkg else 'no'}")
            with pipeline_notice_scope(lambda title, msg: self.pipeline_warning.emit(title, msg)):
                out = pipeline_run_once(
                    settings=self.settings,
                    prebuilt_pkg=self.prebuilt_pkg,
                    prebuilt_sources=self.prebuilt_sources,
                    prebuilt_prompts=self.prebuilt_prompts,
                    prebuilt_seeds=self.prebuilt_seeds,
                    run_control=self.run_control,
                    series_context=self.series_context,
                    on_progress=lambda tid, ov, tk, msg: self.progress.emit(
                        str(tid), int(ov), int(tk), str(msg)
                    ),
                )
            if out is None:
                self.done.emit("")
                dprint("workers", "PipelineWorker done", "empty path")
            else:
                self.done.emit(str(out))
                dprint("workers", "PipelineWorker done", str(out)[:240])
        except PipelineCancelled:
            dprint("workers", "PipelineWorker cancelled")
            self.cancelled.emit()
        except BaseException as e:
            _reraise_system_interrupt(e)
            dprint("workers", "PipelineWorker failed", str(e)[:300])
            tb = traceback.format_exc()
            try:
                from debug import log_pipeline_exception

                log_pipeline_exception("PipelineWorker.run", e, extra="run_once worker thread")
            except Exception:
                pass
            if isinstance(e, QuantDowngradeExhaustedError):
                self.failed.emit(str(e))
            else:
                self.failed.emit(_failure_text_with_cuda_hints(e, tb))

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
            paths = get_paths()
            models = get_models()
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
                _hl = (
                    "Fetching creepypasta sources…"
                    if str(cm).strip().lower() == "creepypasta"
                    else (
                        "Fetching headlines…"
                        if video_format_skips_seen_url_disk_cache(cm)
                        else "Reading news cache…"
                    )
                )
                self.progress.emit("headlines", 0, -1, _hl)
                fc = _firecrawl_kwargs(app)
                if video_format_skips_seen_url_disk_cache(cm):
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
            dprint("workers", "PreviewWorker done", f"confidence={confidence}")
            self.done.emit(pkg, sources, prompts, picked.preset.id, confidence)
        except PipelineCancelled:
            dprint("workers", "PreviewWorker cancelled")
            self.cancelled.emit()
        except BaseException as e:
            _reraise_system_interrupt(e)
            dprint("workers", "PreviewWorker failed", str(e)[:300])
            tb = traceback.format_exc()
            self.failed.emit(_failure_text_with_cuda_hints(e, tb))
        finally:
            try:
                from src.util.cuda_device_policy import resolve_diffusion_cuda_device_index, resolve_llm_cuda_device_index

                release_between_stages(
                    "preview_worker_finally",
                    cuda_device_index=resolve_llm_cuda_device_index(self.settings),
                    variant="prepare_diffusion",
                )
            except Exception:
                pass

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
            paths = get_paths()
            models = get_models()
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
                    tr = topic_research_digest_for_script(paths.data_dir, vf)
                    ri = raw_inst[:8000]
                    extra_md = f"{tr}\n\n{ri}" if tr.strip() and ri.strip() else (tr.strip() or ri)
                    script_digest, _, diffusion_ref_path, script_ref_notes = build_script_context(
                        topic_tags=tags,
                        source_titles=[first_line],
                        stored_firecrawl_key=str(getattr(app, "firecrawl_api_key", "") or ""),
                        firecrawl_enabled=bool(getattr(app, "firecrawl_enabled", False)),
                        want_web=bool(getattr(app.video, "story_web_context", False)),
                        want_refs=bool(getattr(app.video, "story_reference_images", False)),
                        out_dir=ctx_dir,
                        extra_markdown=extra_md,
                        video_format=vf,
                    )
                if str(vf).strip().lower() == "health_advice":
                    vid = getattr(app, "video", None)
                    w = int(getattr(vid, "width", 1080) or 1080) if vid is not None else 1080
                    h = int(getattr(vid, "height", 1920) or 1920) if vid is not None else 1920
                    orient = "portrait (9:16 typical)" if h >= w else "landscape (16:9 typical)"
                    res_block = (
                        f"## Video export target\nFrame size: **{w}×{h}** pixels ({orient}). "
                        "Compose each `visual_prompt` for this output frame shape.\n\n"
                    )
                    script_digest = res_block + (script_digest or "").strip()

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
                        app_settings=app,
                        llm_cuda_device_index=resolve_llm_cuda_device_index(app),
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
                _hl = (
                    "Fetching creepypasta sources…"
                    if str(cm).strip().lower() == "creepypasta"
                    else (
                        "Fetching headlines…"
                        if video_format_skips_seen_url_disk_cache(cm)
                        else "Reading news cache…"
                    )
                )
                self.progress.emit("headlines", 0, -1, _hl)
                fc = _firecrawl_kwargs(app)
                if video_format_skips_seen_url_disk_cache(cm):
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
                    tr = topic_research_digest_for_script(paths.data_dir, vf)
                    ax = (article_excerpt or "")[:12000]
                    extra_md = f"{tr}\n\n{ax}" if tr.strip() and ax.strip() else (tr.strip() or ax)
                    script_digest, _, diffusion_ref_path, script_ref_notes = build_script_context(
                        topic_tags=tags,
                        source_titles=titles,
                        stored_firecrawl_key=str(getattr(app, "firecrawl_api_key", "") or ""),
                        firecrawl_enabled=bool(getattr(app, "firecrawl_enabled", False)),
                        want_web=bool(getattr(app.video, "story_web_context", False)),
                        want_refs=bool(getattr(app.video, "story_reference_images", False)),
                        out_dir=ctx_dir,
                        extra_markdown=extra_md,
                        video_format=vf,
                    )
                if str(vf).strip().lower() == "health_advice":
                    vid = getattr(app, "video", None)
                    w = int(getattr(vid, "width", 1080) or 1080) if vid is not None else 1080
                    h = int(getattr(vid, "height", 1920) or 1920) if vid is not None else 1920
                    orient = "portrait (9:16 typical)" if h >= w else "landscape (16:9 typical)"
                    res_block = (
                        f"## Video export target\nFrame size: **{w}×{h}** pixels ({orient}). "
                        "Compose each `visual_prompt` for this output frame shape.\n\n"
                    )
                    script_digest = res_block + (script_digest or "").strip()

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
                        app_settings=app,
                        llm_cuda_device_index=resolve_llm_cuda_device_index(app),
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

            from src.util.cuda_device_policy import resolve_diffusion_cuda_device_index

            release_between_stages(
                "storyboard_worker_after_script_before_previews",
                cuda_device_index=resolve_diffusion_cuda_device_index(app),
                variant="prepare_diffusion",
            )

            safe_dir = safe_title_to_dirname(pkg.title)
            _mm_sb = str(getattr(app, "media_mode", "video") or "video").strip().lower()
            video_dir = media_output_root(paths, _mm_sb) / safe_dir
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
                video_format=vf,
            )
            self.progress.emit("storyboard_build", 100, -1, "Storyboard structured")

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
                scene_paths = []
                for i, pr in enumerate(prompts):
                    _img_pct(int(100 * i / max(len(prompts), 1)), f"API still {i + 1}/{len(prompts)}…")
                    data = generate_still_png_bytes(settings=app, prompt=str(pr or ""))
                    pth = previews_dir / f"prev_{i + 1:02d}.png"
                    pth.write_bytes(data)
                    scene_paths.append(pth)
            else:
                from src.util.cuda_device_policy import resolve_diffusion_cuda_device_index

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
                    cuda_device_index=resolve_diffusion_cuda_device_index(app),
                    inference_settings=app,
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
            dprint("workers", "StoryboardWorker done", str(manifest))
            self.done.emit(manifest, grid)
        except PipelineCancelled:
            dprint("workers", "StoryboardWorker cancelled")
            self.cancelled.emit()
        except BaseException as e:
            _reraise_system_interrupt(e)
            dprint("workers", "StoryboardWorker failed", str(e)[:300])
            tb = traceback.format_exc()
            self.failed.emit(_failure_text_with_cuda_hints(e, tb))
        finally:
            try:
                from src.util.cuda_device_policy import resolve_diffusion_cuda_device_index

                release_between_stages(
                    "storyboard_worker_finally",
                    cuda_device_index=resolve_diffusion_cuda_device_index(self.settings),
                    variant="cheap",
                )
            except Exception:
                pass
