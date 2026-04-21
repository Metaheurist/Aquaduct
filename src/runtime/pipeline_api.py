from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from src.content.brain import VideoPackage, clip_article_excerpt, enforce_arc
from src.content.brain_api import expand_custom_video_instructions_openai
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
from src.content.personality_auto import auto_pick_personality
from src.content.topics import effective_topic_tags, news_cache_mode_for_run, video_format_skips_seen_url_disk_cache
from src.core.config import AppSettings, VideoSettings, get_models, get_paths, media_output_root, safe_title_to_dirname
from src.render.branding_video import apply_palette_to_prompts
from src.render.editor import assemble_generated_clips_then_concat, assemble_microclips_then_concat
from src.render.utils_ffmpeg import ensure_ffmpeg, find_ffmpeg
from src.runtime.api_generation import generate_still_png_bytes, replicate_video_mp4_paths
from src.runtime.generation_facade import get_generation_facade
from src.runtime.model_backend import assert_api_runtime_ready, is_api_mode
from src.runtime.preflight import preflight_check
from src.speech.elevenlabs_tts import effective_elevenlabs_api_key, elevenlabs_available_for_app
from src.speech.tts_text import shape_tts_text
from src.speech.voice import synthesize, synthesize_unhinged_rotating_pyttsx3
from src.speech.audio_fx import (
    AudioPolishConfig,
    MusicMixConfig,
    duration_seconds,
    ensure_builtin_sfx,
    mix_voice_and_music,
    process_voice_wav,
    render_sfx_track,
    schedule_sfx_events,
    build_sfx_mix_cmd,
)
from src.runtime.pipeline_control import PipelineRunControl
from debug import dprint


def _firecrawl_kwargs(app: AppSettings) -> dict:
    return dict(
        firecrawl_enabled=bool(getattr(app, "firecrawl_enabled", False)),
        firecrawl_api_key=str(getattr(app, "firecrawl_api_key", "") or ""),
    )


def _pipe_progress(
    on_progress: Callable[[str, int, int, str], None] | None,
    overall_pct: int,
    task_pct: int,
    message: str,
) -> None:
    import main as m

    m._pipe_progress(on_progress, overall_pct, task_pct, message)


def _write_video_folder(
    *,
    pkg: VideoPackage,
    video_dir: Path,
    sources: list[dict[str, str]],
    prompts: list[str],
    preview: dict | None = None,
) -> None:
    import main as m

    m._write_video_folder(pkg=pkg, video_dir=video_dir, sources=sources, prompts=prompts, preview=preview)


def _rc(run: PipelineRunControl | None) -> None:
    if run is not None:
        run.checkpoint()


def run_once_api(
    *,
    settings: AppSettings | None = None,
    prebuilt_pkg: VideoPackage | None = None,
    prebuilt_sources: list[dict[str, str]] | None = None,
    prebuilt_prompts: list[str] | None = None,
    prebuilt_seeds: list[int] | None = None,
    run_control: PipelineRunControl | None = None,
    on_progress: Callable[[str, int, int, str], None] | None = None,
) -> Path | None:
    """API execution mode — HTTP providers for LLM / image / voice; Replicate optional for Pro video."""
    paths = get_paths()
    models = get_models()
    app = settings or AppSettings()
    if not is_api_mode(app):
        raise RuntimeError("run_once_api called while not in API mode.")
    assert_api_runtime_ready(app)

    video_settings = app.video
    dprint("pipeline", "run_once_api start", f"slideshow={bool(video_settings.use_image_slideshow)}")
    _pipe_progress(on_progress, 2, -1, "Starting (API mode)…")

    paths.news_cache_dir.mkdir(parents=True, exist_ok=True)
    paths.runs_dir.mkdir(parents=True, exist_ok=True)
    paths.videos_dir.mkdir(parents=True, exist_ok=True)
    paths.pictures_dir.mkdir(parents=True, exist_ok=True)
    _mm_out = str(getattr(app, "media_mode", "video") or "video").strip().lower()
    _projects_root = media_output_root(paths, _mm_out)
    _projects_root.mkdir(parents=True, exist_ok=True)

    if not find_ffmpeg(paths.ffmpeg_dir):
        dprint("pipeline", "Downloading FFmpeg…")
        ensure_ffmpeg(paths.ffmpeg_dir)

    pf = preflight_check(settings=app, strict=True)
    if not pf.ok:
        raise RuntimeError("Preflight failed:\n- " + "\n- ".join(pf.errors))

    _rc(run_control)
    _pipe_progress(on_progress, 6, -1, "Preflight OK (API)")

    from src.core.config import SCRIPT_HEADLINE_FETCH_LIMIT

    items = None
    sources: list[dict[str, str]] = []
    preview_blob: dict | None = None
    item = None

    if prebuilt_pkg is None:
        if str(getattr(app, "run_content_mode", "preset")) == "custom":
            raw_inst = str(getattr(app, "custom_video_instructions", "") or "").strip()
            if not raw_inst:
                _pipe_progress(on_progress, 8, -1, "No instructions (custom mode)")
                return None
            first_line = raw_inst.splitlines()[0].strip()[:120] or "Custom video"
            sources = [{"title": first_line, "url": "", "source": "custom"}]
            items = []
        else:
            fc = _firecrawl_kwargs(app)
            tags = effective_topic_tags(app)
            cm = news_cache_mode_for_run(app)
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
                _pipe_progress(on_progress, 8, -1, "No new headlines in cache")
                return None
            sources = [news_item_to_script_source(it) for it in items]
    else:
        sources = list(prebuilt_sources or [])
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
    article_text = ""
    if prebuilt_pkg is None and item is not None and bool(getattr(video_settings, "fetch_article_text", True)):
        try:
            article_text = fetch_article_text(str(getattr(item, "url", "") or ""), **_firecrawl_kwargs(app))
        except Exception:
            article_text = ""

    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_dir = paths.runs_dir / run_id
    run_assets = run_dir / "assets"
    run_assets.mkdir(parents=True, exist_ok=True)
    if article_text:
        try:
            (run_assets / "article.txt").write_text(article_text, encoding="utf-8")
        except Exception:
            pass

    _vf_cast = str(getattr(app, "video_format", "news") or "news")
    _tags_cast = list(effective_topic_tags(app))
    _head_seed = str(sources[0].get("title") or "") if sources else ""
    active_character = resolve_character_for_pipeline(
        app,
        video_format=_vf_cast,
        topic_tags=_tags_cast,
        headline_seed=_head_seed,
    )
    char_ctx = character_context_for_brain(active_character)

    if prebuilt_pkg is None:
        tags = list(effective_topic_tags(app))
        vf = str(getattr(app, "video_format", "news") or "news")
        llm_id = (app.llm_model_id or "").strip() or models.llm_id
        script_digest = ""
        if str(getattr(app, "run_content_mode", "preset")) == "custom":
            raw_inst = str(app.custom_video_instructions or "").strip()
            titles_for_pick = [sources[0].get("title", "Custom video")] if sources else ["Custom video"]
            picked = auto_pick_personality(
                requested_id=getattr(app, "personality_id", "auto"),
                llm_model_id=llm_id,
                titles=titles_for_pick,
                topic_tags=tags,
                extra_scoring_text=raw_inst[:2000],
            )

            def _llm_api(task: str, pct: int, msg: str) -> None:
                if on_progress is None:
                    return
                inner = max(0, min(100, int(pct)))
                overall = 10 + int(8 * inner / 100)
                _pipe_progress(on_progress, overall, inner, msg or "LLM…")

            expanded = expand_custom_video_instructions_openai(
                settings=app,
                raw_instructions=raw_inst,
                video_format=vf,
                personality_id=picked.preset.id,
                on_llm_task=_llm_api,
            )
            pkg = get_generation_facade(app).generate_script_package(
                settings=app,
                model_id=llm_id,
                items=sources,
                topic_tags=tags,
                personality_id=picked.preset.id,
                branding=getattr(app, "branding", None),
                character_context=char_ctx,
                creative_brief=expanded,
                video_format=vf,
                try_llm_4bit=bool(getattr(app, "try_llm_4bit", True)),
                article_excerpt=clip_article_excerpt(article_text),
                supplement_context=script_digest,
                on_llm_task=_llm_api,
            )
            pkg = enforce_arc(pkg, video_format=vf)
            personality_pick = picked
        else:
            titles = [it.get("title", "") for it in sources if isinstance(it, dict)]
            picked = auto_pick_personality(
                requested_id=getattr(app, "personality_id", "auto"),
                llm_model_id=llm_id,
                titles=titles,
                topic_tags=tags,
                extra_scoring_text="",
            )

            def _llm_api2(task: str, pct: int, msg: str) -> None:
                if on_progress is None:
                    return
                inner = max(0, min(100, int(pct)))
                _pipe_progress(on_progress, 18 + inner // 4, inner, msg or "OpenAI script…")

            article_excerpt = ""
            if bool(getattr(video_settings, "fetch_article_text", True)) and item is not None:
                try:
                    article_excerpt = clip_article_excerpt(
                        fetch_article_text(str(getattr(item, "url", "") or ""), **_firecrawl_kwargs(app))
                    )
                except Exception:
                    article_excerpt = ""

            pkg = get_generation_facade(app).generate_script_package(
                settings=app,
                model_id=llm_id,
                items=sources,
                topic_tags=tags,
                personality_id=picked.preset.id,
                branding=getattr(app, "branding", None),
                character_context=char_ctx,
                creative_brief=None,
                video_format=vf,
                try_llm_4bit=bool(getattr(app, "try_llm_4bit", True)),
                article_excerpt=article_excerpt,
                supplement_context="",
                on_llm_task=_llm_api2,
            )
            pkg = enforce_arc(pkg, video_format=vf)
            personality_pick = picked
    else:
        pkg = prebuilt_pkg
        personality_pick = auto_pick_personality(
            requested_id=getattr(app, "personality_id", "auto"),
            llm_model_id=(app.llm_model_id or "").strip() or models.llm_id,
            titles=[str(pkg.title or "Short video")],
            topic_tags=list(effective_topic_tags(app)),
            extra_scoring_text="",
        )

    assert personality_pick is not None

    if not character_selected_in_settings(app):
        vf_cast2 = str(getattr(app, "video_format", "news") or "news")
        cast = fallback_cast_for_show(
            video_format=vf_cast2, topic_tags=list(effective_topic_tags(app)), headline_seed=_head_seed
        )
        try:
            if cast:
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
    _pipe_progress(on_progress, 44, -1, f"Script ready (API) — {personality_pick.preset.label}")

    safe_dir = safe_title_to_dirname(pkg.title)
    video_dir = _projects_root / safe_dir
    assets_dir = video_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    voice_wav = assets_dir / "voice.wav"
    captions_json = assets_dir / "captions.json"
    vf_voice = str(getattr(app, "video_format", "news") or "news").strip().lower()
    narration = pkg.narration_text()
    pid_voice = effective_personality_id

    vcfg = getattr(getattr(app, "api_models", None), "voice", None)
    vprov = str(getattr(vcfg, "provider", "") or "").strip().lower()
    vmodel = str(getattr(vcfg, "model", "") or "").strip()
    vid_voice = str(getattr(vcfg, "voice_id", "") or "").strip()

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
        if (active_character.elevenlabs_voice_id or "").strip() and elevenlabs_available_for_app(app):
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
    rotate_unhinged = vf_voice == "unhinged" and not use_el and not char_forces_voice and vprov != "openai"

    _pipe_progress(on_progress, 50, -1, "Voice (API / local)…")
    if vprov == "openai" and vmodel:
        from src.platform.openai_client import build_openai_client_from_settings

        client = build_openai_client_from_settings(app)
        vv = vid_voice or "alloy"
        client.speech_to_file(model=vmodel, text=narration, voice=vv, out_path=str(voice_wav))
        try:
            dur = float(duration_seconds(voice_wav))
        except Exception:
            dur = max(30.0, len(narration) / 14.0)
        words = [w for w in narration.split() if w][:240]
        step = dur / max(len(words), 1)
        cap = [{"word": w, "start": i * step, "end": (i + 1) * step} for i, w in enumerate(words)]
        captions_json.write_text(json.dumps(cap), encoding="utf-8")
    elif rotate_unhinged:
        parts: list[str] = []
        if pkg.hook.strip():
            parts.append(pkg.hook.strip())
        for seg in pkg.segments or []:
            if (seg.narration or "").strip():
                parts.append(seg.narration.strip())
        if pkg.cta.strip():
            parts.append(pkg.cta.strip())
        texts_uh: list[str] = []
        for raw in parts:
            st = shape_tts_text(raw, personality_id=pid_voice)
            texts_uh.append(st if st else raw)
        if not texts_uh:
            st_full = shape_tts_text(narration, personality_id=pid_voice)
            texts_uh = [st_full if st_full else narration]
        synthesize_unhinged_rotating_pyttsx3(
            kokoro_model_id=models.kokoro_id,
            segment_texts=texts_uh,
            out_wav_path=voice_wav,
            out_captions_json=captions_json,
        )
    else:
        shaped = shape_tts_text(narration, personality_id=pid_voice)
        if shaped:
            narration = shaped
        synthesize(
            kokoro_model_id=models.kokoro_id,
            text=narration,
            out_wav_path=voice_wav,
            out_captions_json=captions_json,
            pyttsx3_voice_id=py_tts_voice,
            kokoro_speaker=kokoro_sp,
            elevenlabs_voice_id=el_vid,
            elevenlabs_api_key=el_key,
            ffmpeg_executable=ffmpeg_exe,
        )

    _pipe_progress(on_progress, 58, -1, "Voice track ready")
    _rc(run_control)

    final_voice_wav = voice_wav
    try:
        ap_mode = str(getattr(video_settings, "audio_polish", "basic") or "basic")
        cfg = AudioPolishConfig(mode=ap_mode)
        processed = assets_dir / "voice_processed.wav"
        final_voice_wav = process_voice_wav(ffmpeg_dir=paths.ffmpeg_dir, in_wav=voice_wav, out_wav=processed, cfg=cfg)
    except Exception:
        final_voice_wav = voice_wav

    prompts = list(prebuilt_prompts or []) if prebuilt_prompts is not None else [s.visual_prompt for s in pkg.segments][:10]
    branding = getattr(app, "branding", None)
    if prebuilt_pkg is None:
        prompts = apply_palette_to_prompts(prompts, branding)

    out_final = video_dir / "final.mp4"
    music = Path(app.background_music_path).resolve() if app.background_music_path else None

    if bool(getattr(video_settings, "pro_mode", False)):
        from main import _split_into_pro_scenes_from_script

        pro_scenes = _split_into_pro_scenes_from_script(
            pkg=pkg,
            prompts=prompts,
            video_format=str(getattr(app, "video_format", "news") or "news"),
        )
        (assets_dir / "pro_prompt.txt").write_text("\n\n".join(pro_scenes), encoding="utf-8")
        _pipe_progress(on_progress, 68, -1, "Text-to-video (API / Replicate)…")
        clip_dir = assets_dir / "pro_clips"
        clip_paths = replicate_video_mp4_paths(settings=app, prompts=pro_scenes, out_dir=clip_dir)
        if not clip_paths:
            raise RuntimeError("API Pro mode produced no video clips.")
        T = float(getattr(video_settings, "pro_clip_seconds", 4.0))
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
        _pipe_progress(on_progress, 91, -1, "Rendering final MP4 (API)…")
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
        _write_video_folder(pkg=pkg, video_dir=video_dir, sources=sources, prompts=prompts, preview=preview_blob)
        _pipe_progress(on_progress, 100, 100, "Done (API)")
        return video_dir

    if not bool(getattr(video_settings, "use_image_slideshow", True)):
        raise RuntimeError("API mode motion pipeline is not implemented — enable slideshow mode or use Pro + Replicate video.")

    img_dir = assets_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    n_img = max(1, int(getattr(video_settings, "images_per_video", 8)))
    storyboard_prompts = prompts[:n_img]
    image_paths: list[Path] = []
    _pipe_progress(on_progress, 68, -1, "Generating stills (API)…")
    for i, pr in enumerate(storyboard_prompts):
        png = generate_still_png_bytes(settings=app, prompt=str(pr or "").strip() or (pkg.title or "vertical video"))
        pth = img_dir / f"img_{i+1:02d}.png"
        pth.write_bytes(png)
        image_paths.append(pth)
    _pipe_progress(on_progress, 80, -1, "Images ready (API)")

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
            mix_wav = mix_voice_and_music(
                ffmpeg_dir=paths.ffmpeg_dir, voice_wav=final_voice_wav, music_path=music, out_wav=mixed, cfg=mix_cfg
            )
        if str(getattr(video_settings, "sfx_mode", "off") or "off") != "off":
            sfx_paths = ensure_builtin_sfx(assets_dir / "sfx")
            dur_s = float(duration_seconds(mix_wav))
            sfx_clip_count = max(3, min(24, int(dur_s / max(1.0, float(video_settings.microclip_max_s)))))
            events = schedule_sfx_events(duration_s=dur_s, clip_count=sfx_clip_count, sfx_paths=sfx_paths)
            sfx_track = assets_dir / "sfx_track.wav"
            render_sfx_track(sr=44100, duration_s=dur_s, events=events, out_wav=sfx_track)
            import subprocess as _sub

            ffmpeg_bin = Path(ensure_ffmpeg(paths.ffmpeg_dir))
            out_final_wav = assets_dir / "final_audio.wav"
            cmd = build_sfx_mix_cmd(ffmpeg=ffmpeg_bin, base_wav=mix_wav, sfx_wavs=[sfx_track], out_wav=out_final_wav)
            _sub.run(cmd, check=True, capture_output=True, text=True)
            mix_wav = out_final_wav
    except Exception:
        mix_wav = final_voice_wav

    _pipe_progress(on_progress, 88, -1, "Rendering micro-scenes & final MP4 (API)…")
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

    if bool(getattr(video_settings, "cleanup_images_after_run", False)):
        for rel in ("images",):
            p = assets_dir / rel
            try:
                if p.exists() and p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass

    _write_video_folder(pkg=pkg, video_dir=video_dir, sources=sources, prompts=prompts, preview=preview_blob)
    _pipe_progress(on_progress, 100, 100, "Done (API)")
    return video_dir
