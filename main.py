from __future__ import annotations
import argparse
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import sys
import shutil
import tempfile
import time

try:
    from src.util.cpu_parallelism import configure_cpu_parallelism

    configure_cpu_parallelism()
except Exception:
    pass

from debug import apply_cli_debug, dprint, log_pipeline_exception, pipeline_console
from src.content.brain import (
    VideoPackage,
    clip_article_excerpt,
    enforce_arc,
    expand_custom_video_instructions,
    generate_cast_from_storyline_llm,
)
from src.content.characters_store import (
    cast_to_ephemeral_character,
    character_context_for_brain,
    character_selected_in_settings,
    fallback_cast_for_show,
    resolve_character_for_pipeline,
)
from src.content.crawler import (
    fetch_article_text,
    fetch_latest_items,
    get_latest_items,
    get_scored_items,
    news_item_to_script_source,
    pick_one_item,
)
from src.content.factcheck import rewrite_with_uncertainty
from src.content.personality_auto import AutoPickResult, auto_pick_personality
from src.content.prompt_conditioning import (
    assign_scene_types,
    condition_prompt,
    default_negative_prompt,
)
from src.content.story_context import build_script_context
from src.content.topic_research_assets import topic_research_digest_for_script
from src.content.story_pipeline import run_multistage_refinement
from src.content.storyboard import build_storyboard, render_preview_grid, write_manifest
from src.content.topics import effective_topic_tags, news_cache_mode_for_run, video_format_skips_seen_url_disk_cache
from src.core.config import (
    AppSettings,
    SCRIPT_HEADLINE_FETCH_LIMIT,
    VideoSettings,
    get_models,
    get_paths,
    media_output_root,
    safe_title_to_dirname,
)
from src.core.models_dir import clear_pipeline_models_dir, models_dir_for_app, set_pipeline_models_dir
from src.render.artist import (
    apply_regenerated_image,
    generate_images,
    is_curated_text2image_repo,
)
from src.render.branding_video import apply_palette_to_prompts
from src.render.clips import extract_pngs_from_mp4, generate_clips
from src.render.editor import (
    assemble_generated_clips_then_concat,
    assemble_microclips_then_concat,
    assemble_pro_frame_sequence_then_concat,
    pro_mode_frame_count,
)
from src.render.frame_quality import is_reject, score_frame
from src.render.utils_ffmpeg import ensure_ffmpeg, find_ffmpeg
from src.runtime.generation_facade import get_generation_facade
from src.runtime.model_backend import is_api_mode
from src.runtime.pipeline_control import PipelineCancelled, PipelineRunControl
from src.runtime.preflight import preflight_check
from src.models.inference_profiles import log_inference_profiles_for_run
from src.util.cuda_capabilities import cuda_device_reported_by_torch
from src.util.cuda_device_policy import (
    resolve_diffusion_cuda_device_index,
    resolve_llm_cuda_device_index,
    resolve_voice_cuda_device_index,
)
from src.settings.ui_settings import load_settings, save_settings
from src.models.hardware import list_cuda_gpus
from src.runtime.oom_retry import retry_stage
from src.speech.audio_fx import (
    AudioPolishConfig,
    MusicMixConfig,
    build_sfx_mix_cmd,
    duration_seconds,
    ensure_builtin_sfx,
    mix_voice_and_music,
    process_voice_wav,
    render_sfx_track,
    schedule_sfx_events,
)
from src.speech.elevenlabs_tts import (
    effective_elevenlabs_api_key,
    elevenlabs_available_for_app,
)
from src.speech.tts_text import merge_moss_character_and_run_personality, shape_tts_text
from src.speech.tts_kokoro_moss import is_kokoro_repo, is_moss_vg_repo
from src.speech.voice import (
    synthesize,
    synthesize_unhinged_moss,
    synthesize_unhinged_rotating_kokoro,
    synthesize_unhinged_rotating_pyttsx3,
)
from src.util.memory_budget import release_between_stages
from src.util.single_instance import single_instance_guard
from src.util.utils_vram import prepare_for_next_model

try:
    from dotenv import load_dotenv
except Exception:  # optional dependency
    load_dotenv = None


_CLI_SUBCOMMANDS = frozenset({"run", "preflight", "config", "models", "tasks", "version"})


def _clear_after_oom() -> None:
    """
    Best-effort: clear VRAM between retries (diffusers/transformers load can fragment VRAM).
    """
    try:
        prepare_for_next_model()
    except Exception:
        pass
    try:
        import gc

        gc.collect()
        gc.collect()
    except Exception:
        pass
    try:
        import torch

        if cuda_device_reported_by_torch():
            try:
                torch.cuda.synchronize()
            except Exception:
                pass
            try:
                for di in range(int(torch.cuda.device_count())):
                    try:
                        with torch.cuda.device(di):
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
            except Exception:
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass
    except Exception:
        pass


def _apply_hf_token_from_saved_settings(saved_settings: AppSettings | None) -> None:
    if saved_settings and bool(getattr(saved_settings, "hf_api_enabled", True)):
        saved_token = str(getattr(saved_settings, "hf_token", "") or "").strip()
        if saved_token and not (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")):
            os.environ["HF_TOKEN"] = saved_token
            os.environ["HUGGINGFACEHUB_API_TOKEN"] = saved_token




def _rc(run: PipelineRunControl | None) -> None:
    if run is not None:
        run.checkpoint()


def _pipe_progress(
    on_progress: Callable[[str, int, int, str], None] | None,
    overall_pct: int,
    task_pct: int,
    message: str,
) -> None:
    """Emit pipeline UI progress: overall 0–100 for the full run; task 0–100 within the current step (-1 = unknown)."""
    if not on_progress:
        return
    try:
        o = max(0, min(100, int(overall_pct)))
        t = int(task_pct)
        if t > 100:
            t = 100
        if t < -1:
            t = -1
        on_progress("pipeline_run", o, t, message)
    except Exception:
        pass


# Last coarse stage label for failure reporting (``run_once`` only).
_PIPELINE_RUN_STAGE: list[str] = ["(before_run)"]


def _run_stage(stage: str, detail: str = "") -> None:
    """Record and echo the current pipeline phase to stderr (always on)."""
    _PIPELINE_RUN_STAGE[0] = stage
    pipeline_console(detail if detail else stage, stage=stage)


def _firecrawl_kwargs(app: AppSettings) -> dict:
    return dict(
        firecrawl_enabled=bool(getattr(app, "firecrawl_enabled", False)),
        firecrawl_api_key=str(getattr(app, "firecrawl_api_key", "") or ""),
    )


def _now_run_id() -> str:
    # Include milliseconds so two pipelines starting in the same UTC second (e.g. Run + queue)
    # do not share the same runs/ folder or run_id.
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y%m%d_%H%M%S") + f"_{dt.microsecond // 1000:03d}"


def _write_video_folder(
    *,
    pkg: VideoPackage,
    video_dir: Path,
    sources: list[dict[str, str]],
    prompts: list[str],
    preview: dict | None = None,
) -> None:
    video_dir.mkdir(parents=True, exist_ok=True)

    (video_dir / "script.txt").write_text(pkg.narration_text(), encoding="utf-8")

    hashtags_text = (
        f"{pkg.title}\n\n"
        f"{pkg.description}\n\n"
        + " ".join(pkg.hashtags)
        + "\n"
    )
    (video_dir / "hashtags.txt").write_text(hashtags_text, encoding="utf-8")

    meta = {
        "title": pkg.title,
        "description": pkg.description,
        "hashtags": pkg.hashtags,
        "sources": sources,
        "prompts": prompts,
        "created_at_utc": datetime.utcnow().isoformat() + "Z",
    }
    (video_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    if preview is not None:
        try:
            (video_dir / "preview.json").write_text(json.dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def _strip_negative_and_noise(prompt: str) -> str:
    s = (prompt or "").strip()
    if "\nNEGATIVE:" in s:
        s = s.split("\nNEGATIVE:", 1)[0].strip()
    # Some prompts contain "negative :" inline after conditioning.
    low = s.lower()
    if " negative :" in low:
        s = s[: low.find(" negative :")].strip()
    if " negative:" in low:
        s = s[: low.find(" negative:")].strip()
    return " ".join(s.split()).strip()


def _cap_words(text: str, n_words: int) -> str:
    parts = [p for p in (text or "").split() if p]
    if len(parts) <= n_words:
        return " ".join(parts).strip()
    return (" ".join(parts[: max(1, int(n_words))])).strip()


_HASHTAG_RE = re.compile(r"(?:^|\s)#[A-Za-z0-9_]{2,40}\b")


def _scrub_spoken_text(text: str, *, video_format: str) -> str:
    """
    Cleanup for TTS/captions: remove hashtags and common broken filler that slips through.
    Keep this conservative—it's a safety net, not a rewriting model.
    """
    vf = (video_format or "news").strip().lower()
    t = str(text or "").strip()
    if not t:
        return ""

    # Remove hashtags from spoken lines (metadata hashtags still exist separately).
    t = _HASHTAG_RE.sub(" ", " " + t).strip()

    # Remove common LLM artifact fragments / banned filler that harm pacing.
    low = t.lower()
    if vf in ("cartoon", "unhinged"):
        # "one of the..." scaffolding tends to appear as broken mid-sentence filler.
        t = re.sub(r"\bthe\s+one\s+of\s+the\b", "the", t, flags=re.IGNORECASE)
        t = re.sub(r"\bone\s+of\s+the\b", "the", t, flags=re.IGNORECASE)
        # Known broken phrase we've observed in runs.
        t = re.sub(r"\bwe[’']?ll\s+often\s+know\b", "we'll see", t, flags=re.IGNORECASE)
        t = re.sub(r"\bat\s+the\s+the\b", "at the", t, flags=re.IGNORECASE)

    # Collapse repeated punctuation and whitespace.
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\.\.\.+", "…", t).strip()
    return t


def _pro_prompt_for_text_to_video(*, pkg: VideoPackage, prompts: list[str]) -> str:
    """
    Build a short Pro prompt that won't exceed CLIP token limits (e.g. ZeroScope ~77 tokens).
    """
    title = " ".join(str(pkg.title or "").split()).strip()
    beats: list[str] = []
    # Prefer narration beats (storyline) for semantic guidance; keep very short.
    for seg in (pkg.segments or [])[:3]:
        t = " ".join(str(getattr(seg, "narration", "") or "").split()).strip()
        if t:
            beats.append(t)
    # Fallback to visual prompts, but strip negatives/conditioning.
    if not beats:
        for p in prompts[:3]:
            t = _strip_negative_and_noise(p)
            if t:
                beats.append(t)
    core = " | ".join(([title] if title else []) + beats)
    core = _strip_negative_and_noise(core)
    # Hard cap — CLIP text encoders are ~77 tokens; words ≠ tokens.
    return _cap_words(core, 40)


def _split_into_pro_scenes_from_script(
    *,
    pkg: VideoPackage,
    prompts: list[str],
    video_format: str = "news",
) -> list[str]:
    """
    Create a list of scene prompts for Pro video, covering the whole script.

    If a beat is too long for CLIP (~77 tokens), we split it into multiple scenes instead of over-condensing.

    News / explainer style anchors scenes with the headline; cartoon / unhinged omits the title so prompts stay
    character-first (matches storyboard + image models).
    """
    vf = str(video_format or "news").strip().lower()
    use_title = vf not in ("cartoon", "unhinged")
    title = (" ".join(str(pkg.title or "").split()).strip()) if use_title else ""
    out: list[str] = []

    def _motion_cue(i: int) -> str:
        # Short cues — CLIP T2V stacks often cap at ~77 tokens for the whole prompt.
        if vf in ("cartoon", "unhinged"):
            cues = (
                "push-in, whip pan",
                "snap zoom, squash-stretch",
                "handheld wobble",
                "dolly blur",
                "lunge to camera",
                "spin smear",
            )
        else:
            cues = (
                "slow push-in",
                "parallax drift",
                "gentle pan",
                "rack focus",
            )
        return cues[int(i) % len(cues)]

    def _push(scene_text: str) -> None:
        st = _strip_negative_and_noise(scene_text)
        if not st:
            return
        # ~40 words targets under 77 CLIP tokens including punctuation.
        _max_scene = 40
        if len(st.split()) <= _max_scene:
            out.append(st)
            return
        words = st.split()
        # Split into chunks; keep continuity by repeating the title prefix.
        chunk = 32
        start = 0
        while start < len(words) and len(out) < 16:
            part = " ".join(words[start : start + chunk]).strip()
            if title:
                part = f"{title} | {part}"
            out.append(_cap_words(part, _max_scene))
            start += chunk

    # Prefer visual prompts for comedy formats (motion models need visual/action cues; narration is not a scene prompt).
    if vf in ("cartoon", "unhinged"):
        segs = list(pkg.segments or [])
        # Hook: reuse first segment visual if present.
        if segs:
            v0 = " ".join(str(getattr(segs[0], "visual_prompt", "") or "").split()).strip()
            if v0:
                _push(f"{v0}, {_motion_cue(len(out))}")
        for seg in segs:
            vis = " ".join(str(getattr(seg, "visual_prompt", "") or "").split()).strip()
            if vis:
                _push(f"{vis}, {_motion_cue(len(out))}")
        # CTA: reuse last segment visual if present; otherwise fall back.
        if segs:
            vlast = " ".join(str(getattr(segs[-1], "visual_prompt", "") or "").split()).strip()
            if vlast:
                _push(f"{vlast}, {_motion_cue(len(out))}")
    else:
        # Prefer script segments as scenes; include hook/CTA as their own scenes.
        if (pkg.hook or "").strip():
            _push(f"{title} | {pkg.hook}" if title else str(pkg.hook).strip())
        for seg in (pkg.segments or []):
            nar = " ".join(str(getattr(seg, "narration", "") or "").split()).strip()
            if nar:
                _push(f"{title} | {nar}" if title else nar)
        if (pkg.cta or "").strip():
            _push(f"{title} | {pkg.cta}" if title else str(pkg.cta).strip())

    # Fallback: use visual prompts if narration is empty.
    if not out:
        for p in prompts:
            t = _strip_negative_and_noise(p)
            if t:
                _push(f"{title} | {t}" if title else t)
            if len(out) >= 8:
                break

    # Keep at least 1 scene.
    if not out:
        out = [_cap_words(title or "cinematic vertical video", 30)]
    return out


def run_once(
    *,
    settings: AppSettings | None = None,
    prebuilt_pkg: VideoPackage | None = None,
    prebuilt_sources: list[dict[str, str]] | None = None,
    prebuilt_prompts: list[str] | None = None,
    prebuilt_seeds: list[int] | None = None,
    run_control: PipelineRunControl | None = None,
    on_progress: Callable[[str, int, int, str], None] | None = None,
) -> Path | None:
    paths = get_paths()
    models = get_models()
    app_in = settings or AppSettings()
    app = app_in
    if is_api_mode(app):
        from src.runtime.pipeline_api import run_once_api

        return run_once_api(
            settings=app,
            prebuilt_pkg=prebuilt_pkg,
            prebuilt_sources=prebuilt_sources,
            prebuilt_prompts=prebuilt_prompts,
            prebuilt_seeds=prebuilt_seeds,
            run_control=run_control,
            on_progress=on_progress,
        )
    video_settings = app.video
    # Video mode always runs Pro (scene-by-scene). Even if settings/CLI payloads contain older values,
    # force the effective settings here so the pipeline stays predictable.
    try:
        mm = str(getattr(app, "media_mode", "video") or "video").strip().lower()
        if mm == "video":
            video_settings = replace(video_settings, pro_mode=True, use_image_slideshow=False)
            app = replace(app, video=video_settings)
    except Exception:
        pass
    set_pipeline_models_dir(models_dir_for_app(app))
    try:
        dprint(
            "pipeline",
            "run_once start",
            f"prebuilt_pkg={'yes' if prebuilt_pkg is not None else 'no'}",
            f"slideshow={bool(video_settings.use_image_slideshow)}",
        )
        _pipe_progress(on_progress, 2, -1, "Starting…")
        _run_stage("starting", "Pipeline started (this log is always on; use --debug for fine-grained categories)")
        llm_id = app.llm_model_id.strip() or models.llm_id
        img_id = app.image_model_id.strip() or models.sdxl_turbo_id
        clip_id = getattr(app, "video_model_id", "").strip()
        voice_id = app.voice_model_id.strip() or models.kokoro_id
        gpus = list_cuda_gpus()
        _diffusion_cuda_idx = resolve_diffusion_cuda_device_index(app)
        _llm_cuda_idx = resolve_llm_cuda_device_index(app)
        _voice_cuda_idx = resolve_voice_cuda_device_index(app)

        # Ensure base dirs exist
        paths.news_cache_dir.mkdir(parents=True, exist_ok=True)
        paths.runs_dir.mkdir(parents=True, exist_ok=True)
        paths.videos_dir.mkdir(parents=True, exist_ok=True)
        paths.pictures_dir.mkdir(parents=True, exist_ok=True)
        _mm_out = str(getattr(app, "media_mode", "video") or "video").strip().lower()
        _projects_root = media_output_root(paths, _mm_out)
        _projects_root.mkdir(parents=True, exist_ok=True)
    
        if not find_ffmpeg(paths.ffmpeg_dir):
            dprint("pipeline", "Downloading FFmpeg to .Aquaduct_data/.cache/ffmpeg/ (first run; needs internet; may take several minutes)…")
            ensure_ffmpeg(paths.ffmpeg_dir)
    
        pf = preflight_check(settings=app, strict=True)
        if not pf.ok:
            dprint("pipeline", "preflight blocked run", str(pf.errors))
            raise RuntimeError("Preflight failed:\n- " + "\n- ".join(pf.errors))
    
        _rc(run_control)
        _pipe_progress(on_progress, 6, -1, "Preflight OK")
        _run_stage("preflight", "Preflight OK — continuing to sources / script")
        try:
            log_inference_profiles_for_run(app)
        except Exception:
            pass

        items = None
        sources: list[dict[str, str]] = []
        preview_blob: dict | None = None
        item = None
    
        if prebuilt_pkg is None:
            if str(getattr(app, "run_content_mode", "preset")) == "custom":
                raw_inst = str(getattr(app, "custom_video_instructions", "") or "").strip()
                if not raw_inst:
                    dprint("pipeline", "custom mode but empty instructions — stopping")
                    _pipe_progress(on_progress, 8, -1, "No instructions (custom mode)")
                    return None
                first_line = raw_inst.splitlines()[0].strip()[:120] or "Custom video"
                sources = [{"title": first_line, "url": "", "source": "custom"}]
                items = []
                dprint("pipeline", "custom mode — synthetic source", f"title={first_line[:80]!r}")
            else:
                # Prefer scored + diversified selection (better signals, fewer duplicates).
                fc = _firecrawl_kwargs(app)
                tags = effective_topic_tags(app)
                cm = news_cache_mode_for_run(app)
                # Unhinged / creepypasta: do not read/write news_cache — fetch fresh each run.
                if video_format_skips_seen_url_disk_cache(cm):
                    if bool(getattr(video_settings, "high_quality_topic_selection", True)):
                        items = get_scored_items(
                            paths.news_cache_dir,
                            limit=SCRIPT_HEADLINE_FETCH_LIMIT,
                            topic_tags=tags,
                            cache_mode=cm,
                            persist_cache=False,
                            **fc,
                        )
                    else:
                        items = fetch_latest_items(
                            limit=SCRIPT_HEADLINE_FETCH_LIMIT, topic_tags=tags, topic_mode=cm, **fc
                        )
                elif bool(getattr(video_settings, "high_quality_topic_selection", True)):
                    items = get_scored_items(
                        paths.news_cache_dir,
                        limit=SCRIPT_HEADLINE_FETCH_LIMIT,
                        topic_tags=tags,
                        cache_mode=cm,
                        **fc,
                    )
                else:
                    items = get_latest_items(
                        paths.news_cache_dir,
                        limit=SCRIPT_HEADLINE_FETCH_LIMIT,
                        topic_tags=tags,
                        cache_mode=cm,
                        **fc,
                    )
                item = pick_one_item(items)
                if not item:
                    dprint("crawler", "no item picked — stopping run_once")
                    _pipe_progress(on_progress, 8, -1, "No new headlines in cache")
                    return None
                dprint("crawler", f"picked {len(items)} candidate(s)", f"primary={getattr(item, 'title', '')[:90]!r}")
                sources = [news_item_to_script_source(it) for it in items]
        else:
            sources = list(prebuilt_sources or [])
            if not sources:
                # Best-effort fallback: we still want meta.json to contain something.
                sources = []
            preview_blob = {
                "title": prebuilt_pkg.title,
                "description": prebuilt_pkg.description,
                "hashtags": list(prebuilt_pkg.hashtags),
                "hook": prebuilt_pkg.hook,
                "cta": prebuilt_pkg.cta,
                "segments": [
                    {
                        "narration": s.narration,
                        "visual_prompt": s.visual_prompt,
                        "on_screen_text": s.on_screen_text,
                    }
                    for s in (prebuilt_pkg.segments or [])
                ],
            }
    
        _rc(run_control)
        if prebuilt_pkg is None:
            if str(getattr(app, "run_content_mode", "preset")) == "custom":
                _pipe_progress(on_progress, 12, -1, "Custom instructions ready")
            else:
                _pipe_progress(on_progress, 12, -1, "Sources ready")
        else:
            _pipe_progress(on_progress, 14, -1, "Using approved script (skips news & LLM)")
    
        run_id = _now_run_id()
        dprint("pipeline", f"run_id={run_id}")
        run_dir = paths.runs_dir / run_id
        run_assets = run_dir / "assets"
        run_assets.mkdir(parents=True, exist_ok=True)
        _run_stage("workspace", f"Run workspace: {run_dir} (intermediate assets under assets/)")

        article_text = ""
        if prebuilt_pkg is None and item is not None and bool(getattr(video_settings, "fetch_article_text", True)):
            _run_stage("article", "Fetching full article text (Firecrawl/crawl; may be empty on failure)")
            try:
                article_text = fetch_article_text(
                    str(getattr(item, "url", "") or ""),
                    **_firecrawl_kwargs(app),
                )
                if article_text:
                    (run_assets / "article.txt").write_text(article_text, encoding="utf-8")
            except Exception:
                article_text = ""
    
        # Cast: if user explicitly selected a character, use it. Otherwise generate an ephemeral narrator/cast per run.
        _vf_cast = str(getattr(app, "video_format", "news") or "news")
        _tags_cast = list(effective_topic_tags(app))
        _head_seed = ""
        if sources:
            _head_seed = str(sources[0].get("title") or "")
        elif prebuilt_pkg is not None:
            _head_seed = str(prebuilt_pkg.title or "")
        active_character = resolve_character_for_pipeline(
            app,
            video_format=_vf_cast,
            topic_tags=_tags_cast,
            headline_seed=_head_seed,
        )
        char_ctx = character_context_for_brain(active_character)
    
        diffusion_reference_image: Path | None = None
    
        personality_pick: AutoPickResult | None = None
    
        # Brain
        if prebuilt_pkg is None:
            tags = list(effective_topic_tags(app))
            vf = str(getattr(app, "video_format", "news") or "news")
            try_llm_4bit = bool(getattr(app, "try_llm_4bit", True))
            script_digest = ""
            script_ref_notes = ""
            if bool(getattr(video_settings, "story_web_context", False)) or bool(
                getattr(video_settings, "story_reference_images", False)
            ):
                _run_stage(
                    "story_web_context",
                    "Building script web context (Firecrawl digest + optional reference downloads)…",
                )
                titles_ctx = [str(s.get("title", "")) for s in sources if isinstance(s, dict)]
                tr_block = topic_research_digest_for_script(paths.data_dir, vf)
                art_block = (article_text or "")[:12000]
                if tr_block.strip() and art_block.strip():
                    extra_md = f"{tr_block.strip()}\n\n## Scraped article\n{art_block.strip()}"
                elif tr_block.strip():
                    extra_md = tr_block.strip()
                else:
                    extra_md = art_block
                script_digest, _scr_paths, diffusion_reference_image, script_ref_notes = build_script_context(
                    topic_tags=tags,
                    source_titles=titles_ctx,
                    stored_firecrawl_key=str(getattr(app, "firecrawl_api_key", "") or ""),
                    firecrawl_enabled=bool(getattr(app, "firecrawl_enabled", False)),
                    want_web=bool(getattr(video_settings, "story_web_context", False)),
                    want_refs=bool(getattr(video_settings, "story_reference_images", False)),
                    out_dir=run_assets,
                    extra_markdown=extra_md,
                    video_format=vf,
                )
                if (script_digest or "").strip():
                    _pipe_progress(on_progress, 16, -1, "Script web context gathered…")
                _run_stage("story_web_context", "Web digest / references materialized under assets/script_context/")

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
    
            def _maybe_multistage(p: VideoPackage) -> VideoPackage:
                if not bool(getattr(video_settings, "story_multistage_enabled", False)):
                    return p
    
                def _ms_llm(task: str, pct: int, msg: str) -> None:
                    if on_progress is None:
                        return
                    inner = max(0, min(100, int(pct)))
                    overall = 24 + int(18 * inner / 100)
                    _pipe_progress(on_progress, overall, inner, msg or "Script refinement…")
    
                _pipe_progress(on_progress, 24, -1, "Multi-stage script refinement…")
                return run_multistage_refinement(
                    p,
                    video_format=vf,
                    model_id=llm_id,
                    web_digest=script_digest,
                    reference_notes=script_ref_notes,
                    try_llm_4bit=try_llm_4bit,
                    on_llm_task=_ms_llm,
                    app_settings=app,
                    llm_cuda_device_index=_llm_cuda_idx,
                )
    
            if str(getattr(app, "run_content_mode", "preset")) == "custom" and str(getattr(app, "custom_video_instructions", "") or "").strip():
                raw_inst = str(app.custom_video_instructions).strip()
                titles_for_pick = [sources[0].get("title", "Custom video")] if sources else ["Custom video"]
                picked = auto_pick_personality(
                    requested_id=getattr(app, "personality_id", "auto"),
                    llm_model_id=llm_id,
                    titles=titles_for_pick,
                    topic_tags=tags,
                    extra_scoring_text=raw_inst[:2000],
                )
    
                def _expand_llm(task: str, pct: int, msg: str) -> None:
                    if on_progress is None:
                        return
                    inner = max(0, min(100, int(pct)))
                    overall = 10 + int(8 * inner / 100)
                    _pipe_progress(on_progress, overall, inner, msg or "Expanding brief…")
    
                _rc(run_control)
                _pipe_progress(on_progress, 14, -1, "Expanding creative brief (LLM)…")
                expanded = expand_custom_video_instructions(
                    model_id=llm_id,
                    raw_instructions=raw_inst,
                    video_format=vf,
                    personality_id=picked.preset.id,
                    character_context=char_ctx,
                    on_llm_task=_expand_llm,
                    try_llm_4bit=try_llm_4bit,
                    llm_cuda_device_index=_llm_cuda_idx,
                    inference_settings=app,
                )
                _pipe_progress(on_progress, 22, -1, "Writing script (LLM)…")
                _run_stage("script_llm", f"Custom run: LLM generating script ({llm_id!r})…")
                def _run_script(s: AppSettings, idx: int | None) -> VideoPackage:
                    return get_generation_facade(s).generate_script_package(
                        settings=s,
                        llm_cuda_device_index=idx,
                        model_id=llm_id,
                        items=sources,
                        topic_tags=tags,
                        personality_id=picked.preset.id,
                        branding=getattr(s, "branding", None),
                        character_context=char_ctx,
                        creative_brief=expanded,
                        video_format=vf,
                        try_llm_4bit=try_llm_4bit,
                        article_excerpt=clip_article_excerpt(article_text),
                        supplement_context=script_digest,
                    )

                pkg, app, _llm_cuda_idx = retry_stage(
                    stage_name="script_custom",
                    role="script",
                    repo_id=str(llm_id),
                    settings=app,
                    cuda_device_index=_llm_cuda_idx,
                    gpus=gpus,
                    clear_cb=_clear_after_oom,
                    run_cb=_run_script,
                )
                pkg = enforce_arc(pkg, video_format=vf)
                pkg = _maybe_multistage(pkg)
                personality_pick = picked
                dprint("pipeline", "script ready (custom)", f"title={pkg.title[:100]!r}")
                _run_stage("script_llm", "Script package ready (custom mode)")
            else:
                titles = [it.get("title", "") for it in sources if isinstance(it, dict)]
                picked = auto_pick_personality(
                    requested_id=getattr(app, "personality_id", "auto"),
                    llm_model_id=llm_id,
                    titles=titles,
                    topic_tags=tags,
                    extra_scoring_text="",
                )
                _pipe_progress(on_progress, 22, -1, "Writing script (LLM)…")
                _run_stage("script_llm", f"Preset run: LLM generating script ({llm_id!r})…")
                def _run_script2(s: AppSettings, idx: int | None) -> VideoPackage:
                    return get_generation_facade(s).generate_script_package(
                        settings=s,
                        llm_cuda_device_index=idx,
                        model_id=llm_id,
                        items=sources,
                        topic_tags=tags,
                        personality_id=picked.preset.id,
                        branding=getattr(s, "branding", None),
                        character_context=char_ctx,
                        video_format=vf,
                        try_llm_4bit=try_llm_4bit,
                        article_excerpt=clip_article_excerpt(article_text),
                        supplement_context=script_digest,
                    )

                pkg, app, _llm_cuda_idx = retry_stage(
                    stage_name="script",
                    role="script",
                    repo_id=str(llm_id),
                    settings=app,
                    cuda_device_index=_llm_cuda_idx,
                    gpus=gpus,
                    clear_cb=_clear_after_oom,
                    run_cb=_run_script2,
                )
                pkg = enforce_arc(pkg, video_format=vf)
                pkg = _maybe_multistage(pkg)
                # Best-effort safety rewrite (uses article text snippet when available).
                if bool(getattr(video_settings, "llm_factcheck", True)):
                    pkg = rewrite_with_uncertainty(
                        pkg=pkg,
                        article_text=article_text,
                        sources=sources,
                        model_id=llm_id,
                        try_llm_4bit=try_llm_4bit,
                        quant_mode=str(getattr(app, "script_quant_mode", "auto") or "auto"),
                        inference_settings=app,
                        llm_cuda_device_index=_llm_cuda_idx,
                    )
                dprint("pipeline", "script ready", f"title={pkg.title[:100]!r}")
                _run_stage("script_llm", "Script package ready (preset mode)")
                personality_pick = picked
        else:
            pkg = prebuilt_pkg
            dprint("pipeline", "using prebuilt script package", f"title={pkg.title[:100]!r}")
            tags_voice = list(effective_topic_tags(app))
            personality_pick = auto_pick_personality(
                requested_id=getattr(app, "personality_id", "auto"),
                llm_model_id=llm_id,
                titles=[str(pkg.title or "Short video")],
                topic_tags=tags_voice,
                extra_scoring_text="",
            )
    
        assert personality_pick is not None
    
        # If the user did NOT select a character, generate a storyline-aligned narrator/cast and store it under the video assets.
        # This keeps cartoon/unhinged runs from using a single generic host, and keeps news/explainer as narrator-only.
        if not character_selected_in_settings(app):
            vf_cast2 = str(getattr(app, "video_format", "news") or "news")
            storyline = pkg.narration_text()
            cast: list[dict] | None = None
            _run_stage("cast_llm", "No fixed character: generating ephemeral cast via LLM (or fallback)")
            try:
    
                def _cast_llm(task: str, pct: int, msg: str) -> None:
                    inner = max(0, min(100, int(pct)))
                    _pipe_progress(on_progress, 34, inner, msg or "Generating cast…")
    
                cast = generate_cast_from_storyline_llm(
                    model_id=llm_id,
                    video_format=vf_cast2,
                    storyline_title=str(pkg.title or ""),
                    storyline_text=storyline,
                    topic_tags=list(effective_topic_tags(app)),
                    on_llm_task=_cast_llm,
                    try_llm_4bit=bool(getattr(app, "try_llm_4bit", True)),
                )
            except Exception:
                cast = fallback_cast_for_show(video_format=vf_cast2, topic_tags=list(effective_topic_tags(app)), headline_seed=_head_seed)
    
            try:
                assert cast is not None
                active_character = cast_to_ephemeral_character(cast=cast, video_format=vf_cast2)
                char_ctx = character_context_for_brain(active_character)
    
                safe_dir_cast = safe_title_to_dirname(pkg.title)
                video_dir_cast = _projects_root / safe_dir_cast
                assets_dir_cast = video_dir_cast / "assets"
                assets_dir_cast.mkdir(parents=True, exist_ok=True)
                (assets_dir_cast / "generated_cast.json").write_text(
                    json.dumps({"video_format": vf_cast2, "characters": cast}, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass
        effective_personality_id = personality_pick.preset.id
        dprint(
            "pipeline",
            "effective personality for voice/TTS",
            effective_personality_id,
            personality_pick.reason,
        )
        _pipe_progress(
            on_progress,
            44,
            -1,
            f"Script ready — tone: {personality_pick.preset.label} ({personality_pick.reason})",
        )
        _rc(run_control)
    
        # Free LLM weights before TTS / diffusion so peak VRAM stays lower (slower overall).
        release_between_stages(
            "after_script_llm_before_voice_or_photo",
            cuda_device_index=_llm_cuda_idx,
            variant="prepare_diffusion",
        )

        safe_dir = safe_title_to_dirname(pkg.title)
        video_dir = _projects_root / safe_dir
        assets_dir = video_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        # Photo mode: generate stills and optional layouts (no voice/captions, no mp4).
        try:
            mm_eff = str(getattr(app, "media_mode", "video") or "video").strip().lower()
        except Exception:
            mm_eff = "video"
        if mm_eff == "photo":
            pic = getattr(app, "picture", None)
            pic_out = str(getattr(pic, "output_type", "single_image") or "single_image")
            pic_fmt = str(getattr(pic, "picture_format", "poster") or "poster")
            n_img = int(getattr(pic, "image_count", 6) or 6)
            n_img = max(1, min(32, n_img))

            _pipe_progress(on_progress, 50, -1, "Photo mode: generating images…")
            _run_stage("photo_diffusion", f"Photo mode: generating {n_img} still(s) with {img_id!r}")
            _rc(run_control)

            sb = build_storyboard(
                pkg,
                seed_base=getattr(video_settings, "seed_base", None),
                branding=getattr(app, "branding", None),
                max_scenes=max(1, min(10, n_img)),
                character=active_character,
                video_format=str(getattr(app, "video_format", "news") or "news"),
            )
            base_prompts = [s.prompt for s in sb.scenes] or ["vertical video, one clear subject, bold composition"]
            base_seeds = [int(s.seed) for s in sb.scenes] or [123]
            prompts_img = [base_prompts[i % len(base_prompts)] for i in range(n_img)]
            seeds_img = [int(base_seeds[i % len(base_seeds)]) + (i // max(1, len(base_seeds))) * 7919 for i in range(n_img)]
            try:
                br = getattr(app, "branding", None)
                if br is not None and bool(getattr(br, "photo_style_enabled", False)):
                    prompts_img = [
                        f"{p}, print-ready design, paper texture, clean negative space, high detail still"
                        for p in prompts_img
                    ]
            except Exception:
                pass

            img_dir = assets_dir / "images"
            def _run_images(s: AppSettings, idx: int | None):
                return generate_images(
                    sdxl_turbo_model_id=img_id,
                    prompts=prompts_img,
                    out_dir=img_dir,
                    max_images=n_img,
                    seeds=seeds_img,
                    allow_nsfw=bool(getattr(s, "allow_nsfw", False)),
                    art_style_preset_id=str(getattr(s, "art_style_preset_id", "balanced") or "balanced"),
                    use_style_continuity=True,
                    cuda_device_index=idx,
                    inference_settings=s,
                )

            gen, app, _diffusion_cuda_idx = retry_stage(
                stage_name="photo_images",
                role="image",
                repo_id=str(img_id),
                settings=app,
                cuda_device_index=_diffusion_cuda_idx,
                gpus=gpus,
                clear_cb=_clear_after_oom,
                run_cb=_run_images,
            )
            img_paths = [g.path for g in gen if getattr(g, "path", None) is not None]
            if not img_paths:
                raise RuntimeError("Photo mode produced no images.")

            out_final_png = video_dir / "final.png"
            if pic_out == "layouted":
                from src.render.layouts import render_layout  # type: ignore

                render_layout(
                    picture_format=pic_fmt,
                    images=img_paths,
                    title=str(getattr(pkg, "title", "") or ""),
                    out_path=out_final_png,
                    size=(int(getattr(pic, "width", 1080) or 1080), int(getattr(pic, "height", 1920) or 1920)),
                    branding=getattr(app, "branding", None),
                )
            elif pic_out == "image_set":
                grid = assets_dir / "preview_grid.png"
                render_preview_grid(scene_paths=img_paths, out_grid=grid, cols=3, thumb=320)
                try:
                    grid.replace(out_final_png)
                except Exception:
                    out_final_png.write_bytes(grid.read_bytes())
            else:
                # single_image (default): copy first image
                try:
                    out_final_png.write_bytes(img_paths[0].read_bytes())
                except Exception:
                    try:
                        import shutil

                        shutil.copy2(img_paths[0], out_final_png)
                    except Exception:
                        pass

            _pipe_progress(on_progress, 93, -1, "Photo export complete")
            # Persist quant adjustments if we auto-downgraded during retries.
            try:
                if app != app_in:
                    save_settings(app)
            except Exception:
                pass
            return out_final_png
    
        # Voice
        _pipe_progress(on_progress, 50, -1, "Generating voice / captions…")
        _run_stage("voice_tts", f"Synthesizing narration ({voice_id!r}); writing voice.wav + captions.json")
        voice_wav = assets_dir / "voice.wav"
        captions_json = assets_dir / "captions.json"
        vf_voice = str(getattr(app, "video_format", "news") or "news").strip().lower()
        narration = _scrub_spoken_text(pkg.narration_text(), video_format=vf_voice)
        pid_voice = effective_personality_id
        py_tts_voice: str | None = None
        kokoro_sp: str | None = None
        el_vid: str | None = None
        el_key: str | None = None
        ffmpeg_exe = None
        if active_character is not None and not active_character.use_default_voice:
            if (active_character.pyttsx3_voice_id or "").strip():
                py_tts_voice = active_character.pyttsx3_voice_id.strip()
            if (active_character.kokoro_voice or "").strip():
                kokoro_sp = active_character.kokoro_voice.strip()
            if (
                (active_character.elevenlabs_voice_id or "").strip()
                and elevenlabs_available_for_app(app)
            ):
                el_vid = active_character.elevenlabs_voice_id.strip()
                el_key = effective_elevenlabs_api_key(app)
                try:
                    ffmpeg_exe = ensure_ffmpeg(paths.ffmpeg_dir)
                except Exception:
                    ffmpeg_exe = None
                    el_vid = None
                    el_key = None
        use_el = bool(el_vid and el_key and ffmpeg_exe)
        char_forces_voice = active_character is not None and not getattr(active_character, "use_default_voice", True)
        rotate_unhinged = vf_voice == "unhinged" and not use_el and not char_forces_voice
        char_moss: str | None = (
            (active_character.voice_instruction or "").strip() if active_character is not None else None
        )
        voice_inst = merge_moss_character_and_run_personality(char_moss, pid_voice)
    
        if rotate_unhinged:
            parts: list[str] = []
            if pkg.hook.strip():
                parts.append(_scrub_spoken_text(pkg.hook.strip(), video_format=vf_voice))
            for seg in pkg.segments or []:
                if (seg.narration or "").strip():
                    parts.append(_scrub_spoken_text(seg.narration.strip(), video_format=vf_voice))
            if pkg.cta.strip():
                parts.append(_scrub_spoken_text(pkg.cta.strip(), video_format=vf_voice))
            texts_uh: list[str] = []
            for raw in parts:
                st = shape_tts_text(raw, personality_id=pid_voice)
                texts_uh.append(st if st else raw)
            if not texts_uh:
                st_full = shape_tts_text(narration, personality_id=pid_voice)
                texts_uh = [st_full if st_full else narration]
            _voice_qm = str(getattr(app, "voice_quant_mode", "auto") or "auto")
            if is_moss_vg_repo(voice_id):
                synthesize_unhinged_moss(
                    kokoro_model_id=voice_id,
                    voice_instruction=voice_inst,
                    segment_texts=texts_uh,
                    out_wav_path=voice_wav,
                    out_captions_json=captions_json,
                    voice_quant_mode=_voice_qm,
                    voice_cuda_device_index=_voice_cuda_idx,
                )
            elif is_kokoro_repo(voice_id):
                synthesize_unhinged_rotating_kokoro(
                    kokoro_model_id=voice_id,
                    segment_texts=texts_uh,
                    out_wav_path=voice_wav,
                    out_captions_json=captions_json,
                    kokoro_speaker=kokoro_sp,
                    voice_quant_mode=_voice_qm,
                )
            else:
                synthesize_unhinged_rotating_pyttsx3(
                    kokoro_model_id=voice_id,
                    segment_texts=texts_uh,
                    out_wav_path=voice_wav,
                    out_captions_json=captions_json,
                )
        else:
            shaped = shape_tts_text(narration, personality_id=pid_voice)
            if shaped:
                try:
                    (assets_dir / "narration_shaped.txt").write_text(shaped, encoding="utf-8")
                    narration = shaped
                except Exception:
                    pass
            synthesize(
                kokoro_model_id=voice_id,
                text=narration,
                out_wav_path=voice_wav,
                out_captions_json=captions_json,
                pyttsx3_voice_id=py_tts_voice,
                kokoro_speaker=kokoro_sp,
                voice_instruction=voice_inst,
                elevenlabs_voice_id=el_vid,
                elevenlabs_api_key=el_key,
                ffmpeg_executable=ffmpeg_exe,
                voice_quant_mode=str(getattr(app, "voice_quant_mode", "auto") or "auto"),
                voice_cuda_device_index=_voice_cuda_idx,
            )
    
        _pipe_progress(on_progress, 58, -1, "Voice track ready")
        _run_stage("voice_tts", "Voice track + captions ready")
        _rc(run_control)

        release_between_stages(
            "after_voice_tts_before_polish",
            cuda_device_index=_diffusion_cuda_idx,
            variant="prepare_diffusion",
        )

        # Audio polish + mixing (FFmpeg best-effort)
        final_voice_wav = voice_wav
        try:
            _run_stage("audio_polish", f"FFmpeg voice polish ({getattr(video_settings, 'audio_polish', 'basic')!r})")
            ap_mode = str(getattr(video_settings, "audio_polish", "basic") or "basic")
            cfg = AudioPolishConfig(mode=ap_mode)
            processed = assets_dir / "voice_processed.wav"
            final_voice_wav = process_voice_wav(ffmpeg_dir=paths.ffmpeg_dir, in_wav=voice_wav, out_wav=processed, cfg=cfg)
            dprint("audio", f"voice polish mode={ap_mode!r}")
        except Exception:
            final_voice_wav = voice_wav
            pipeline_console("Voice polish skipped (using raw voice.wav)", stage="audio_polish")

        release_between_stages("after_voice_polish_before_visuals", variant="cheap")

        # Images
        prompts = list(prebuilt_prompts or []) if prebuilt_prompts is not None else [s.visual_prompt for s in pkg.segments][:10]
        seeds = list(prebuilt_seeds or []) if prebuilt_seeds is not None else None
        out_final = video_dir / "final.mp4"
        music = Path(app.background_music_path).resolve() if app.background_music_path else None
        branding = getattr(app, "branding", None)
        if prebuilt_pkg is None:
            prompts = apply_palette_to_prompts(prompts, branding)
            dprint("branding", "apply_palette_to_prompts", f"n={len(prompts)}")
    
        # Prebuilt image prompts: apply character visuals here (storyboard path for fresh runs uses build_storyboard).
        if prebuilt_prompts is not None and active_character is not None and (active_character.visual_style or "").strip():
            vs = active_character.visual_style.strip()
            prompts = [f"{vs}, {p}" if (p or "").strip() else vs for p in prompts]
    
        # Scene-type conditioning + variety (best-effort).
        if bool(getattr(video_settings, "prompt_conditioning", True)):
            try:
                scene_types = assign_scene_types(prompts)
                neg = default_negative_prompt()
                if prebuilt_prompts is not None and active_character is not None and (active_character.negatives or "").strip():
                    extra = active_character.negatives.strip()
                    neg = f"{neg}, {extra}" if neg else extra
                    if len(neg) > 3000:
                        neg = neg[:3000]
                prompts = [condition_prompt(p, scene_type=scene_types[i], idx=i, negatives=neg) for i, p in enumerate(prompts)]
            except Exception:
                pass
    
        _pipe_progress(on_progress, 64, -1, "Preparing visuals & prompts…")
        _rc(run_control)
    
        _allow_nsfw = bool(getattr(app, "allow_nsfw", False))
        _art_style_id = str(getattr(app, "art_style_preset_id", None) or "balanced")
        _diffusion_ref_kw: dict = {}
        if (
            diffusion_reference_image is not None
            and diffusion_reference_image.exists()
            and bool(getattr(video_settings, "story_reference_images", False))
        ):
            _diffusion_ref_kw = {
                "external_reference_image": diffusion_reference_image,
                "external_reference_strength": 0.55,
            }
    
        # Pro mode: scene-by-scene video — text-to-video (Video slot) and/or image model → img2vid (e.g. SVD).
        if bool(getattr(video_settings, "pro_mode", False)):
            vid_slot = (clip_id or "").strip()
            if not vid_slot:
                raise RuntimeError("Pro mode requires a Video (motion) model on the Model tab (e.g. ZeroScope).")
            lowv = vid_slot.lower()
            pro_img2vid = "stable-video-diffusion" in lowv or "img2vid" in lowv
            try:
                vf_tip = str(getattr(app, "video_format", "news") or "news").strip().lower()
                if vf_tip in ("cartoon", "unhinged", "creepypasta", "health_advice") and pro_img2vid:
                    _pipe_progress(
                        on_progress,
                        64,
                        -1,
                        "Tip: img→vid models (e.g. SVD) can look like a ‘live photo’. For stronger motion, try Video model: ZeroScope (text→video).",
                    )
            except Exception:
                pass

            T = float(getattr(video_settings, "pro_clip_seconds", 4.0))
            T = max(0.5, T)
            pro_scenes = _split_into_pro_scenes_from_script(
                pkg=pkg,
                prompts=prompts,
                video_format=str(getattr(app, "video_format", "news") or "news"),
            )
            # Persist the exact prompts used for debugging.
            (assets_dir / "pro_prompt.txt").write_text("\n\n".join(pro_scenes), encoding="utf-8")
            # Persist the full Pro configuration for reproducibility/debugging.
            try:
                pro_manifest = {
                    "title": str(pkg.title or ""),
                    "video_format": str(getattr(app, "video_format", "news") or "news"),
                    "models": {
                        "llm": str(llm_id or ""),
                        "image": str(img_id or ""),
                        "video": str(vid_slot or ""),
                        "voice": str(voice_id or ""),
                    },
                    "video_settings": dict(vars(video_settings)),
                    "pro": {
                        "pro_mode": True,
                        "pro_img2vid": bool(pro_img2vid),
                        "pro_clip_seconds": float(T),
                        "fps": int(getattr(video_settings, "fps", 30)),
                        "seed_base": getattr(video_settings, "seed_base", None),
                        "n_scenes": int(len(pro_scenes)),
                        "scene_prompts": list(pro_scenes),
                    },
                }
                (assets_dir / "pro_manifest.json").write_text(
                    json.dumps(pro_manifest, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass

            if pro_img2vid:
                _pipe_progress(on_progress, 64, -1, "Pro: scene keyframes (image model)…")
                _run_stage("diffusion_image", f"Pro img2vid: still keyframes with image model {img_id!r}")
                _rc(run_control)
                key_dir = assets_dir / "pro_keyframes"
                pro_storyboard = build_storyboard(
                    pkg,
                    seed_base=getattr(video_settings, "seed_base", None),
                    branding=getattr(app, "branding", None),
                    max_scenes=max(1, len(pro_scenes)),
                    character=active_character,
                    video_format=str(getattr(app, "video_format", "news") or "news"),
                )
                ns = max(1, len(pro_storyboard.scenes))
                pro_key_seeds = [
                    int(pro_storyboard.scenes[i % ns].seed) + (i // ns) * 7919 for i in range(len(pro_scenes))
                ]
                def _run_pro_keyframes(s: AppSettings, idx: int | None):
                    return generate_images(
                        sdxl_turbo_model_id=img_id,
                        prompts=pro_scenes,
                        out_dir=key_dir,
                        max_images=len(pro_scenes),
                        seeds=pro_key_seeds,
                        allow_nsfw=_allow_nsfw,
                        art_style_preset_id=_art_style_id,
                        use_style_continuity=True,
                        cuda_device_index=idx,
                        inference_settings=s,
                        **_diffusion_ref_kw,
                    )

                key_gen, app, _diffusion_cuda_idx = retry_stage(
                    stage_name="pro_keyframes",
                    role="image",
                    repo_id=str(img_id),
                    settings=app,
                    cuda_device_index=_diffusion_cuda_idx,
                    gpus=gpus,
                    clear_cb=_clear_after_oom,
                    run_cb=_run_pro_keyframes,
                )
                keyframes = [g.path for g in key_gen]
                release_between_stages(
                    "after_pro_keyframes_before_img2vid",
                    cuda_device_index=_diffusion_cuda_idx,
                    variant="prepare_diffusion",
                )
                _pipe_progress(on_progress, 68, -1, "Pro: image-to-video (motion model)…")
                _run_stage("video_motion", f"Pro img2vid: motion model {vid_slot!r} (load + encode per scene)")
                _rc(run_control)
                clip_dir = assets_dir / "pro_clips"
                def _run_pro_i2v(s: AppSettings, idx: int | None):
                    return generate_clips(
                        video_model_id=vid_slot,
                        prompts=pro_scenes,
                        init_images=keyframes,
                        out_dir=clip_dir,
                        max_clips=len(pro_scenes),
                        fps=int(video_settings.fps),
                        seconds_per_clip=T,
                        cuda_device_index=idx,
                        inference_settings=s,
                    )

                gen_clips, app, _diffusion_cuda_idx = retry_stage(
                    stage_name="pro_i2v",
                    role="video",
                    repo_id=str(vid_slot),
                    settings=app,
                    cuda_device_index=_diffusion_cuda_idx,
                    gpus=gpus,
                    clear_cb=_clear_after_oom,
                    run_cb=_run_pro_i2v,
                    max_quant_downgrades=8,
                )
            else:
                # Large local T2V (e.g. Wan 14B) spikes host RAM during shard load; drop retained VRAM/heap first.
                release_between_stages(
                    "before_pro_text_to_video_load",
                    cuda_device_index=_diffusion_cuda_idx,
                    variant="prepare_diffusion",
                )
                _pipe_progress(on_progress, 68, -1, "Text-to-video (Pro)…")
                _run_stage(
                    "video_t2v",
                    f"Pro text-to-video: {vid_slot!r} — loading diffusers pipeline (first load can take many minutes)",
                )
                _rc(run_control)
                clip_dir = assets_dir / "pro_clips"
                def _run_pro_t2v(s: AppSettings, idx: int | None):
                    return generate_clips(
                        video_model_id=vid_slot,
                        prompts=pro_scenes,
                        init_images=None,
                        out_dir=clip_dir,
                        max_clips=len(pro_scenes),
                        fps=int(video_settings.fps),
                        seconds_per_clip=T,
                        cuda_device_index=idx,
                        inference_settings=s,
                    )

                gen_clips, app, _diffusion_cuda_idx = retry_stage(
                    stage_name="pro_t2v",
                    role="video",
                    repo_id=str(vid_slot),
                    settings=app,
                    cuda_device_index=_diffusion_cuda_idx,
                    gpus=gpus,
                    clear_cb=_clear_after_oom,
                    run_cb=_run_pro_t2v,
                    max_quant_downgrades=8,
                )
            clip_paths = [c.path for c in gen_clips]
            if not clip_paths:
                raise RuntimeError("Pro mode produced no video segments.")

            release_between_stages("pro_after_video_diffusion_before_timeline_align", variant="cheap")

            # Align narration to the total Pro timeline so captions and audio match the generated clip duration.
            total_T = float(T) * float(len(clip_paths))
            mix_wav = final_voice_wav
            try:
                ffmpeg_bin = Path(ensure_ffmpeg(paths.ffmpeg_dir))
                aligned = assets_dir / "voice_pro_timeline.wav"
                from src.render.editor import _ffmpeg_align_wav_to_duration  # type: ignore
    
                _ffmpeg_align_wav_to_duration(ffmpeg_bin, final_voice_wav, aligned, total_T)
                mix_wav = aligned
            except Exception:
                mix_wav = final_voice_wav
    
            _pipe_progress(on_progress, 91, -1, "Rendering Pro video & final MP4…")
            _run_stage("encode", "FFmpeg/MoviePy: mux clips + captions + audio → final.mp4")
            _rc(run_control)
            assemble_generated_clips_then_concat(
                ffmpeg_dir=paths.ffmpeg_dir,
                settings=video_settings,
                clips=clip_paths,
                voice_wav=mix_wav,
                captions_json=captions_json,
                out_final_mp4=out_final,
                out_assets_dir=assets_dir,
                background_music=None,
                branding=branding,
                article_text=article_text,
                topic_tags=list(effective_topic_tags(app)),
                video_format=str(getattr(app, "video_format", "news") or "news"),
            )
            _pipe_progress(on_progress, 93, -1, "Encode complete")
            try:
                if app != app_in:
                    save_settings(app)
            except Exception:
                pass
            return out_final
    
        if video_settings.use_image_slideshow:
            _pro = bool(getattr(video_settings, "pro_mode", False))
            n_pro = (
                pro_mode_frame_count(
                    pro_clip_seconds=float(getattr(video_settings, "pro_clip_seconds", 4.0)),
                    fps=int(video_settings.fps),
                )
                if _pro
                else 0
            )
            dprint(
                "pipeline",
                "mode=slideshow",
                f"pro_mode={_pro}",
                f"images_per_video={video_settings.images_per_video}",
                f"n_pro_frames={n_pro}" if _pro else "",
            )
            img_dir = assets_dir / "images"
            if prebuilt_prompts is not None:
                if _pro:
                    head_n = min(32, max(1, len(prompts)), n_pro)
                    storyboard_prompts_head = prompts[:head_n]
                    storyboard_seeds = (seeds or [])[:head_n]
                    if len(storyboard_seeds) < len(storyboard_prompts_head):
                        base = getattr(video_settings, "seed_base", None)
                        base_i = int(base) if base is not None else 123
                        storyboard_seeds = storyboard_seeds + [
                            base_i + (i + 1) * 9973 for i in range(len(storyboard_prompts_head) - len(storyboard_seeds))
                        ]
                    storyboard = build_storyboard(
                        pkg,
                        seed_base=getattr(video_settings, "seed_base", None),
                        branding=getattr(app, "branding", None),
                        max_scenes=len(storyboard_prompts_head),
                        character=active_character,
                        video_format=str(getattr(app, "video_format", "news") or "news"),
                    )
                    try:
                        for i in range(min(len(storyboard.scenes), len(storyboard_prompts_head))):
                            sc = storyboard.scenes[i]
                            storyboard.scenes[i] = type(sc)(  # type: ignore[misc]
                                **{**sc.__dict__, "prompt": storyboard_prompts_head[i], "seed": int(storyboard_seeds[i])}
                            )
                    except Exception:
                        pass
                    ns = max(1, len(storyboard.scenes))
                    storyboard_prompts = [storyboard.scenes[i % ns].prompt for i in range(n_pro)]
                    storyboard_seeds = [int(storyboard.scenes[i % ns].seed) + (i // ns) * 7919 for i in range(n_pro)]
                else:
                    storyboard_prompts = prompts[: max(1, int(video_settings.images_per_video))]
                    storyboard_seeds = (seeds or [])[: len(storyboard_prompts)]
                    if len(storyboard_seeds) < len(storyboard_prompts):
                        base = getattr(video_settings, "seed_base", None)
                        base_i = int(base) if base is not None else 123
                        storyboard_seeds = storyboard_seeds + [
                            base_i + (i + 1) * 9973 for i in range(len(storyboard_prompts) - len(storyboard_seeds))
                        ]
                    storyboard = build_storyboard(
                        pkg,
                        seed_base=getattr(video_settings, "seed_base", None),
                        branding=getattr(app, "branding", None),
                        max_scenes=len(storyboard_prompts),
                        character=active_character,
                        video_format=str(getattr(app, "video_format", "news") or "news"),
                    )
                    try:
                        for i in range(min(len(storyboard.scenes), len(storyboard_prompts))):
                            sc = storyboard.scenes[i]
                            storyboard.scenes[i] = type(sc)(  # type: ignore[misc]
                                **{**sc.__dict__, "prompt": storyboard_prompts[i], "seed": int(storyboard_seeds[i])}
                            )
                    except Exception:
                        pass
            else:
                if _pro:
                    sb_cap = min(32, max(3, n_pro))
                    storyboard = build_storyboard(
                        pkg,
                        seed_base=getattr(video_settings, "seed_base", None),
                        branding=getattr(app, "branding", None),
                        max_scenes=sb_cap,
                        character=active_character,
                        video_format=str(getattr(app, "video_format", "news") or "news"),
                    )
                    ns = max(1, len(storyboard.scenes))
                    storyboard_prompts = [storyboard.scenes[i % ns].prompt for i in range(n_pro)]
                    storyboard_seeds = [int(storyboard.scenes[i % ns].seed) + (i // ns) * 7919 for i in range(n_pro)]
                else:
                    storyboard = build_storyboard(
                        pkg,
                        seed_base=getattr(video_settings, "seed_base", None),
                        branding=getattr(app, "branding", None),
                        max_scenes=max(1, int(video_settings.images_per_video)),
                        character=active_character,
                        video_format=str(getattr(app, "video_format", "news") or "news"),
                    )
                    storyboard_prompts = [s.prompt for s in storyboard.scenes]
                    storyboard_seeds = [s.seed for s in storyboard.scenes]
            manifest_path = assets_dir / "manifest.json"
            write_manifest(
                manifest_path,
                storyboard=storyboard,
                settings={
                    "video": dict(vars(video_settings)),
                    "models": {"llm": llm_id, "img": img_id, "clip": (clip_id or ""), "voice": voice_id},
                },
            )
            _pipe_progress(on_progress, 68, -1, "Generating images (diffusion)…")
            _run_stage("diffusion_image", f"Slideshow / Pro stills: image model {img_id!r}")

            def _gen_images_retry(
                *,
                model_id: str,
                prompts: list[str],
                out_dir: Path,
                max_images: int,
                seeds: list[int] | None,
                use_style_continuity: bool,
                allow_nsfw: bool,
                art_style_preset_id: str,
                extra_kw: dict,
            ):
                nonlocal app, _diffusion_cuda_idx

                def _run(s: AppSettings, idx: int | None):
                    return generate_images(
                        sdxl_turbo_model_id=model_id,
                        prompts=prompts,
                        out_dir=out_dir,
                        max_images=max_images,
                        seeds=seeds,
                        allow_nsfw=allow_nsfw,
                        art_style_preset_id=art_style_preset_id,
                        use_style_continuity=use_style_continuity,
                        cuda_device_index=idx,
                        inference_settings=s,
                        **(extra_kw or {}),
                    )

                out, app2, idx2 = retry_stage(
                    stage_name="images",
                    role="image",
                    repo_id=str(model_id),
                    settings=app,
                    cuda_device_index=_diffusion_cuda_idx,
                    gpus=gpus,
                    clear_cb=_clear_after_oom,
                    run_cb=_run,
                )
                app = app2
                _diffusion_cuda_idx = idx2
                return out

            def _gen_clips_retry(
                *,
                video_model_id: str,
                prompts: list[str],
                init_images: list[Path] | None,
                out_dir: Path,
                max_clips: int,
                fps: int,
                seconds_per_clip: float,
            ):
                nonlocal app, _diffusion_cuda_idx

                def _run(s: AppSettings, idx: int | None):
                    return generate_clips(
                        video_model_id=video_model_id,
                        prompts=prompts,
                        init_images=init_images,
                        out_dir=out_dir,
                        max_clips=max_clips,
                        fps=fps,
                        seconds_per_clip=seconds_per_clip,
                        cuda_device_index=idx,
                        inference_settings=s,
                    )

                out, app2, idx2 = retry_stage(
                    stage_name="clips",
                    role="video",
                    repo_id=str(video_model_id),
                    settings=app,
                    cuda_device_index=_diffusion_cuda_idx,
                    gpus=gpus,
                    clear_cb=_clear_after_oom,
                    run_cb=_run,
                    max_quant_downgrades=8,
                )
                app = app2
                _diffusion_cuda_idx = idx2
                return out

            gen_max = n_pro if _pro else max(1, int(video_settings.images_per_video))
            vid_slot = (clip_id or "").strip()
            if _pro:
                if not vid_slot:
                    raise RuntimeError(
                        "Pro mode requires a Video (motion) model on the Model tab — e.g. ZeroScope (text-to-video) "
                        "or a text-to-image repo id if you want per-frame stills from the Video slot."
                    )
                lowv = vid_slot.lower()
                if is_curated_text2image_repo(vid_slot):
                    gen = _gen_images_retry(
                        model_id=vid_slot,
                        prompts=storyboard_prompts,
                        out_dir=img_dir,
                        max_images=gen_max,
                        seeds=storyboard_seeds,
                        allow_nsfw=_allow_nsfw,
                        art_style_preset_id=_art_style_id,
                        use_style_continuity=False,
                        extra_kw=_diffusion_ref_kw,
                    )
                    image_paths = [g.path for g in gen]
                elif "zeroscope" in lowv:
                    merged = " ".join((p or "").strip() for p in storyboard_prompts[:6] if (p or "").strip())[:900]
                    if not merged.strip():
                        merged = (pkg.title or "cinematic vertical video").strip()[:500]
                    tmp_clip = assets_dir / "pro_zeroscope"
                    tmp_clip.mkdir(parents=True, exist_ok=True)
                    _pipe_progress(on_progress, 70, -1, "Text-to-video (Pro)…")
                    zc = _gen_clips_retry(
                        video_model_id=vid_slot,
                        prompts=[merged],
                        init_images=None,
                        out_dir=tmp_clip,
                        max_clips=1,
                        fps=int(video_settings.fps),
                        seconds_per_clip=float(getattr(video_settings, "pro_clip_seconds", 4.0)),
                    )
                    if not zc:
                        raise RuntimeError("Pro mode produced no video segments (ZeroScope path).")
                    img_dir.mkdir(parents=True, exist_ok=True)
                    for old in img_dir.glob("img_*.png"):
                        try:
                            old.unlink()
                        except OSError:
                            pass
                    image_paths = extract_pngs_from_mp4(
                        zc[0].path,
                        img_dir,
                        n=gen_max,
                        ffmpeg_dir=paths.ffmpeg_dir,
                    )
                elif "stable-video-diffusion" in lowv or "img2vid" in lowv:
                    # Slideshow Pro expects still frames; SVD cannot fill that slot — use the Image model for stills.
                    gen = _gen_images_retry(
                        model_id=img_id,
                        prompts=storyboard_prompts,
                        out_dir=img_dir,
                        max_images=gen_max,
                        seeds=storyboard_seeds,
                        allow_nsfw=_allow_nsfw,
                        art_style_preset_id=_art_style_id,
                        use_style_continuity=False,
                        extra_kw=_diffusion_ref_kw,
                    )
                    image_paths = [g.path for g in gen]
                else:
                    gen = _gen_images_retry(
                        model_id=vid_slot,
                        prompts=storyboard_prompts,
                        out_dir=img_dir,
                        max_images=gen_max,
                        seeds=storyboard_seeds,
                        allow_nsfw=_allow_nsfw,
                        art_style_preset_id=_art_style_id,
                        use_style_continuity=False,
                        extra_kw=_diffusion_ref_kw,
                    )
                    image_paths = [g.path for g in gen]
            else:
                gen = _gen_images_retry(
                    model_id=img_id,
                    prompts=storyboard_prompts,
                    out_dir=img_dir,
                    max_images=gen_max,
                    seeds=storyboard_seeds,
                    allow_nsfw=_allow_nsfw,
                    art_style_preset_id=_art_style_id,
                    use_style_continuity=True,
                    extra_kw=_diffusion_ref_kw,
                )
                image_paths = [g.path for g in gen]
            _pipe_progress(on_progress, 80, -1, "Images ready")

            release_between_stages("slideshow_after_diffusion_before_audio_mix", variant="cheap")

            # Quality reject/regenerate (best-effort; pro mode skips — too many frames).
            retries = max(0, int(getattr(video_settings, "quality_retries", 2)))
            if retries > 0 and not _pro:
                for si, (p, base_seed, out_path) in enumerate(zip(storyboard_prompts, storyboard_seeds, image_paths), start=1):
                    attempt = 0
                    while attempt < retries:
                        try:
                            q = score_frame(out_path)
                            if not is_reject(q):
                                break
                        except Exception:
                            break
                        attempt += 1
                        with tempfile.TemporaryDirectory(prefix="aquaduct_regen_") as _td:
                            regen = generate_images(
                                sdxl_turbo_model_id=img_id,
                                prompts=[p],
                                out_dir=Path(_td),
                                max_images=1,
                                seeds=[int(base_seed) + attempt],
                                allow_nsfw=_allow_nsfw,
                                art_style_preset_id=_art_style_id,
                                use_style_continuity=False,
                                cuda_device_index=_diffusion_cuda_idx,
                                inference_settings=app,
                            )
                            if regen:
                                apply_regenerated_image(regen, out_path)
    
            # Update manifest with image paths
            try:
                import json as _json
    
                mp = assets_dir / "manifest.json"
                m = _json.loads(mp.read_text(encoding="utf-8"))
                for i, pth in enumerate(image_paths, start=1):
                    try:
                        m["scenes"][i - 1]["image_path"] = str(pth)
                    except Exception:
                        pass
                if _pro:
                    m["pro_generated_frames"] = len(image_paths)
                mp.write_text(_json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
    
            # If music/SFX are enabled, pre-mix into a final wav and pass it as voice_wav, to avoid double-mixing.
            mix_wav = final_voice_wav
            try:
                if music and music.exists():
                    mix_cfg = MusicMixConfig(
                        enabled=True,
                        ducking_enabled=bool(getattr(video_settings, "music_ducking", True)),
                        ducking_amount=float(getattr(video_settings, "music_ducking_amount", 0.7)),
                        fade_s=float(getattr(video_settings, "music_fade_s", 1.2)),
                        music_volume=float(getattr(video_settings, "music_volume", 0.08)),
                    )
                    mixed = assets_dir / "audio_bed.wav"
                    mix_wav = mix_voice_and_music(ffmpeg_dir=paths.ffmpeg_dir, voice_wav=final_voice_wav, music_path=music, out_wav=mixed, cfg=mix_cfg)
                if str(getattr(video_settings, "sfx_mode", "off") or "off") != "off":
                    sfx_paths = ensure_builtin_sfx(assets_dir / "sfx")
                    dur_s = float(duration_seconds(mix_wav))
                    sfx_clip_count = (
                        max(3, min(24, int(dur_s / max(1.0, float(video_settings.microclip_max_s)))))
                        if _pro
                        else len(image_paths)
                    )
                    events = schedule_sfx_events(duration_s=dur_s, clip_count=sfx_clip_count, sfx_paths=sfx_paths)
                    sfx_track = assets_dir / "sfx_track.wav"
                    render_sfx_track(sr=44100, duration_s=dur_s, events=events, out_wav=sfx_track)
                    import subprocess as _sub
                    from pathlib import Path as _Path
    
                    ffmpeg_bin = _Path(ensure_ffmpeg(paths.ffmpeg_dir))
                    out_final_wav = assets_dir / "final_audio.wav"
                    cmd = build_sfx_mix_cmd(ffmpeg=ffmpeg_bin, base_wav=mix_wav, sfx_wavs=[sfx_track], out_wav=out_final_wav)
                    _sub.run(cmd, check=True, capture_output=True, text=True)
                    mix_wav = out_final_wav
            except Exception:
                mix_wav = final_voice_wav
    
            _pipe_progress(
                on_progress,
                88,
                -1,
                "Rendering Pro frame sequence & final MP4…" if _pro else "Rendering micro-scenes & final MP4…",
            )
            _rc(run_control)
    
            if _pro:
                assemble_pro_frame_sequence_then_concat(
                    ffmpeg_dir=paths.ffmpeg_dir,
                    settings=video_settings,
                    images=image_paths,
                    voice_wav=mix_wav,
                    captions_json=captions_json,
                    out_final_mp4=out_final,
                    out_assets_dir=assets_dir,
                    timeline_seconds=float(getattr(video_settings, "pro_clip_seconds", 4.0)),
                    background_music=None,
                    branding=branding,
                    article_text=article_text,
                    topic_tags=list(effective_topic_tags(app)),
                    video_format=str(getattr(app, "video_format", "news") or "news"),
                )
            else:
                assemble_microclips_then_concat(
                    ffmpeg_dir=paths.ffmpeg_dir,
                    settings=video_settings,
                    images=image_paths,
                    voice_wav=mix_wav,
                    captions_json=captions_json,
                    out_final_mp4=out_final,
                    out_assets_dir=assets_dir,
                    background_music=None,
                    branding=branding,
                    article_text=article_text,
                    topic_tags=list(effective_topic_tags(app)),
                    video_format=str(getattr(app, "video_format", "news") or "news"),
                )
            _pipe_progress(on_progress, 93, -1, "Encode complete")
        else:
            # For img→vid models, first generate keyframe images (using the image model),
            # then animate them into scene segments with the selected video model.
            dprint("pipeline", "mode=video_clips", f"clips_per_video={video_settings.clips_per_video}")
            key_dir = assets_dir / "keyframes"
            storyboard = build_storyboard(
                pkg,
                seed_base=getattr(video_settings, "seed_base", None),
                branding=getattr(app, "branding", None),
                max_scenes=max(1, int(video_settings.clips_per_video)),
                character=active_character,
                video_format=str(getattr(app, "video_format", "news") or "news"),
            )
            storyboard_prompts = [s.prompt for s in storyboard.scenes]
            storyboard_seeds = [s.seed for s in storyboard.scenes]
            manifest_path = assets_dir / "manifest.json"
            write_manifest(
                manifest_path,
                storyboard=storyboard,
                settings={"video": dict(vars(video_settings)), "models": {"llm": llm_id, "img": img_id, "clip": (clip_id or img_id), "voice": voice_id}},
            )
            _pipe_progress(on_progress, 68, -1, "Generating keyframe images…")
            _run_stage("diffusion_image", f"Motion mode: keyframe stills with {img_id!r}")
            def _run_keyframes(s: AppSettings, idx: int | None):
                return generate_images(
                    sdxl_turbo_model_id=img_id,
                    prompts=storyboard_prompts,
                    out_dir=key_dir,
                    max_images=max(1, int(video_settings.clips_per_video)),
                    seeds=storyboard_seeds,
                    allow_nsfw=_allow_nsfw,
                    art_style_preset_id=_art_style_id,
                    cuda_device_index=idx,
                    inference_settings=s,
                    **_diffusion_ref_kw,
                )

            key_gen, app, _diffusion_cuda_idx = retry_stage(
                stage_name="keyframes",
                role="image",
                repo_id=str(img_id),
                settings=app,
                cuda_device_index=_diffusion_cuda_idx,
                gpus=gpus,
                clear_cb=_clear_after_oom,
                run_cb=_run_keyframes,
            )
            keyframes = [g.path for g in key_gen]
            _pipe_progress(on_progress, 76, -1, "Keyframes ready")
    
            retries = max(0, int(getattr(video_settings, "quality_retries", 2)))
            if retries > 0:
                for si, (p, base_seed, out_path) in enumerate(zip(storyboard_prompts, storyboard_seeds, keyframes), start=1):
                    attempt = 0
                    while attempt < retries:
                        try:
                            q = score_frame(out_path)
                            if not is_reject(q):
                                break
                        except Exception:
                            break
                        attempt += 1
                        with tempfile.TemporaryDirectory(prefix="aquaduct_regen_") as _td:
                            def _run_regen(s: AppSettings, idx: int | None):
                                return generate_images(
                                    sdxl_turbo_model_id=img_id,
                                    prompts=[p],
                                    out_dir=Path(_td),
                                    max_images=1,
                                    seeds=[int(base_seed) + attempt],
                                    allow_nsfw=_allow_nsfw,
                                    art_style_preset_id=_art_style_id,
                                    use_style_continuity=False,
                                    cuda_device_index=idx,
                                    inference_settings=s,
                                )

                            regen, app, _diffusion_cuda_idx = retry_stage(
                                stage_name="keyframe_regen",
                                role="image",
                                repo_id=str(img_id),
                                settings=app,
                                cuda_device_index=_diffusion_cuda_idx,
                                gpus=gpus,
                                clear_cb=_clear_after_oom,
                                run_cb=_run_regen,
                            )
                            if regen:
                                apply_regenerated_image(regen, out_path)
    
            # Update manifest with keyframe paths
            try:
                import json as _json
    
                mp = assets_dir / "manifest.json"
                m = _json.loads(mp.read_text(encoding="utf-8"))
                for i, pth in enumerate(keyframes, start=1):
                    try:
                        m["scenes"][i - 1]["image_path"] = str(pth)
                    except Exception:
                        pass
                mp.write_text(_json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
    
            _rc(run_control)
    
            # Keyframe image model off GPU before loading the clip / video diffusion model.
            release_between_stages(
                "motion_after_keyframes_before_clip_diffusion",
                cuda_device_index=_diffusion_cuda_idx,
                variant="prepare_diffusion",
            )

            clip_dir = assets_dir / "clips"
            _pipe_progress(on_progress, 82, -1, "Video diffusion (animate scenes)…")
            _vid_id = (clip_id or img_id)
            _run_stage("video_motion", f"Motion mode: img2vid / scene clips with {_vid_id!r}")

            def _run_scene_clips(s: AppSettings, idx: int | None):
                return generate_clips(
                    video_model_id=_vid_id,
                    prompts=prompts,
                    init_images=keyframes,
                    out_dir=clip_dir,
                    max_clips=max(1, int(video_settings.clips_per_video)),
                    fps=int(video_settings.fps),
                    seconds_per_clip=float(video_settings.clip_seconds),
                    cuda_device_index=idx,
                    inference_settings=s,
                )

            gen_clips, app, _diffusion_cuda_idx = retry_stage(
                stage_name="scene_clips",
                role="video",
                repo_id=str(_vid_id),
                settings=app,
                cuda_device_index=_diffusion_cuda_idx,
                gpus=gpus,
                clear_cb=_clear_after_oom,
                run_cb=_run_scene_clips,
                max_quant_downgrades=8,
            )
            clip_paths = [c.path for c in gen_clips]
            _pipe_progress(on_progress, 88, -1, "Scenes ready")

            release_between_stages("motion_after_scene_clips_before_audio_mux", variant="cheap")

            mix_wav = final_voice_wav
            try:
                if music and music.exists():
                    mix_cfg = MusicMixConfig(
                        enabled=True,
                        ducking_enabled=bool(getattr(video_settings, "music_ducking", True)),
                        ducking_amount=float(getattr(video_settings, "music_ducking_amount", 0.7)),
                        fade_s=float(getattr(video_settings, "music_fade_s", 1.2)),
                        music_volume=float(getattr(video_settings, "music_volume", 0.08)),
                    )
                    mixed = assets_dir / "audio_bed.wav"
                    mix_wav = mix_voice_and_music(ffmpeg_dir=paths.ffmpeg_dir, voice_wav=final_voice_wav, music_path=music, out_wav=mixed, cfg=mix_cfg)
            except Exception:
                mix_wav = final_voice_wav
    
            _pipe_progress(on_progress, 91, -1, "Rendering micro-scenes & final MP4…")
            _run_stage("encode", "Motion mode: assembling clips + captions → final.mp4")
            _rc(run_control)
    
            assemble_generated_clips_then_concat(
                ffmpeg_dir=paths.ffmpeg_dir,
                settings=video_settings,
                clips=clip_paths,
                voice_wav=mix_wav,
                captions_json=captions_json,
                out_final_mp4=out_final,
                out_assets_dir=assets_dir,
                background_music=None,
                branding=branding,
                article_text=article_text,
                topic_tags=list(effective_topic_tags(app)),
                video_format=str(getattr(app, "video_format", "news") or "news"),
            )
            _pipe_progress(on_progress, 93, -1, "Encode complete")
    
        # Optional cleanup: remove large image/keyframe folders to save disk space.
        if bool(getattr(video_settings, "cleanup_images_after_run", False)):
            for rel in ("images", "keyframes"):
                p = assets_dir / rel
                try:
                    if p.exists() and p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                except Exception:
                    pass
    
        _pipe_progress(on_progress, 97, -1, "Saving project folder…")
        _run_stage("export", f"Writing meta.json, script.txt, hashtags → {video_dir}")
        _write_video_folder(pkg=pkg, video_dir=video_dir, sources=sources, prompts=prompts, preview=preview_blob)
        _pipe_progress(on_progress, 100, 100, "Done")
        dprint("pipeline", "run_once done", f"video_dir={video_dir}")
        _run_stage("done", f"Run finished successfully → {video_dir}")
        try:
            if app != app_in:
                save_settings(app)
        except Exception:
            pass
        return video_dir
    except BaseException as e:
        try:
            log_pipeline_exception(
                _PIPELINE_RUN_STAGE[0],
                e,
                extra="If this is CUDA OOM, try a lighter Video model profile or lower quant on the Model tab.",
            )
        except Exception:
            pass
        raise
    finally:
        clear_pipeline_models_dir()


def main() -> None:
    if load_dotenv:
        load_dotenv()

    argv = sys.argv[1:]
    if argv and argv[0] == "help":
        from src.cli.parser import build_parser

        build_parser().print_help()
        raise SystemExit(0)
    if argv and argv[0] in _CLI_SUBCOMMANDS:
        from src.cli.main import main as cli_main

        raise SystemExit(cli_main(argv))

    single_instance_guard()

    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", action="store_true", help="Launch the desktop UI.")
    ap.add_argument("--cli", action="store_true", help="Run the CLI pipeline (default is UI).")
    ap.add_argument("--once", action="store_true", help="Run a single generation cycle and exit.")
    ap.add_argument("--interval-hours", type=float, default=4.0, help="Polling interval in hours.")
    ap.add_argument("--music", type=str, default="", help="Optional background music file path.")
    ap.add_argument(
        "--debug",
        type=str,
        default="",
        help="Debug categories (comma-separated) or 'all'. Merges with env AQUADUCT_DEBUG. See debug/debug_log.py.",
    )
    args = ap.parse_args()

    if args.debug:
        apply_cli_debug(args.debug)

    music = Path(args.music).resolve() if args.music else None

    # Always load so saved HF token / hub prefs apply before UI or `--once`, not only `--cli`/`--once`.
    # (`UI/app.py` + `MainWindow` load again for theme/widgets — path is the same `settings_path()`.)
    saved_settings = load_settings()
    if saved_settings and bool(getattr(saved_settings, "hf_api_enabled", True)):
        saved_token = str(getattr(saved_settings, "hf_token", "") or "").strip()
        if saved_token and not (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")):
            os.environ["HF_TOKEN"] = saved_token
            os.environ["HUGGINGFACEHUB_API_TOKEN"] = saved_token

    # Default: launching main should bring up the UI (unless CLI mode requested).
    if args.ui or (not args.cli and not args.once):
        from UI.app import main as ui_main

        ui_main()
        return

    if args.once:
        app = saved_settings or AppSettings()
        if music:
            app = replace(app, background_music_path=str(music))
        out = run_once(settings=app)
        if out:
            print(f"Created: {out}")
        else:
            print("No new items found.")
        return

    interval_s = max(60.0, args.interval_hours * 3600.0)
    while True:
        try:
            saved_loop = load_settings()
            _apply_hf_token_from_saved_settings(saved_loop)
            app = saved_loop or AppSettings()
            if music:
                app = replace(app, background_music_path=str(music))
            out = run_once(settings=app)
            if out:
                print(f"Created: {out}")
            else:
                print("No new items found.")
        except Exception as e:
            print(f"Run failed: {e}")
        time.sleep(interval_s)


if __name__ == "__main__":
    main()

