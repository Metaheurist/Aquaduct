from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # optional dependency
    load_dotenv = None

from src.artist import generate_images
from src.brain import VideoPackage, generate_script
from src.config import AppSettings, VideoSettings, get_models, get_paths, safe_title_to_dirname
from src.crawler import get_latest_items, pick_one_item
from src.editor import assemble_generated_clips_then_concat, assemble_microclips_then_concat
from src.clips import generate_clips
from src.voice import synthesize
from src.preflight import preflight_check
from src.personality_auto import auto_pick_personality


def _single_instance_guard(name: str = "Aquaduct") -> None:
    """
    Prevent multiple instances from running at the same time.
    On Windows, uses a named mutex. Else, uses an exclusive lock file in the project cache dir.
    """
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            mutex = kernel32.CreateMutexW(None, True, f"Global\\{name}")
            last_err = kernel32.GetLastError()
            # 183 = ERROR_ALREADY_EXISTS
            if mutex and int(last_err) == 183:
                raise SystemExit(f"{name} is already running.")
            return
        except SystemExit:
            raise
        except Exception:
            # Fall back to lock file below
            pass

    try:
        import msvcrt  # type: ignore
    except Exception:
        msvcrt = None  # type: ignore

    paths = get_paths()
    lock_path = paths.cache_dir / f"{name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+", encoding="utf-8")
    try:
        if msvcrt:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # type: ignore

            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        raise SystemExit(f"{name} is already running.")


def _now_run_id() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _write_video_folder(
    *,
    pkg: VideoPackage,
    video_dir: Path,
    sources: list[dict[str, str]],
    prompts: list[str],
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


def run_once(*, settings: AppSettings | None = None) -> Path | None:
    paths = get_paths()
    models = get_models()
    app = settings or AppSettings(topic_tags=[])
    video_settings = app.video
    llm_id = app.llm_model_id.strip() or models.llm_id
    img_id = app.image_model_id.strip() or models.sdxl_turbo_id
    clip_id = getattr(app, "video_model_id", "").strip()
    voice_id = app.voice_model_id.strip() or models.kokoro_id

    # Ensure base dirs exist
    paths.news_cache_dir.mkdir(parents=True, exist_ok=True)
    paths.runs_dir.mkdir(parents=True, exist_ok=True)
    paths.videos_dir.mkdir(parents=True, exist_ok=True)

    pf = preflight_check(settings=app, strict=True)
    if not pf.ok:
        raise RuntimeError("Preflight failed:\n- " + "\n- ".join(pf.errors))

    items = get_latest_items(paths.news_cache_dir, limit=3, topic_tags=app.topic_tags)
    item = pick_one_item(items)
    if not item:
        return None

    run_id = _now_run_id()
    run_dir = paths.runs_dir / run_id
    run_assets = run_dir / "assets"
    run_assets.mkdir(parents=True, exist_ok=True)

    # Brain
    sources = [{"title": it.title, "url": it.url, "source": it.source} for it in items]
    titles = [it.get("title", "") for it in sources if isinstance(it, dict)]
    picked = auto_pick_personality(
        requested_id=getattr(app, "personality_id", "auto"),
        llm_model_id=llm_id,
        titles=titles,
        topic_tags=list(app.topic_tags),
    )
    pkg = generate_script(
        model_id=llm_id,
        items=sources,
        topic_tags=app.topic_tags,
        personality_id=picked.preset.id,
    )

    safe_dir = safe_title_to_dirname(pkg.title)
    video_dir = paths.videos_dir / safe_dir
    assets_dir = video_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Voice
    voice_wav = assets_dir / "voice.wav"
    captions_json = assets_dir / "captions.json"
    narration = pkg.narration_text()
    synthesize(
        kokoro_model_id=voice_id,
        text=narration,
        out_wav_path=voice_wav,
        out_captions_json=captions_json,
    )

    # Images
    prompts = [s.visual_prompt for s in pkg.segments][:10]
    out_final = video_dir / "final.mp4"
    music = Path(app.background_music_path).resolve() if app.background_music_path else None
    branding = getattr(app, "branding", None)

    if video_settings.use_image_slideshow:
        img_dir = assets_dir / "images"
        gen = generate_images(
            sdxl_turbo_model_id=img_id,
            prompts=prompts,
            out_dir=img_dir,
            max_images=max(1, int(video_settings.images_per_video)),
        )
        image_paths = [g.path for g in gen]
        assemble_microclips_then_concat(
            ffmpeg_dir=paths.ffmpeg_dir,
            settings=video_settings,
            images=image_paths,
            voice_wav=voice_wav,
            captions_json=captions_json,
            out_final_mp4=out_final,
            out_assets_dir=assets_dir,
            background_music=music,
            branding=branding,
        )
    else:
        # For img→vid clip models, first generate keyframe images (using the image model),
        # then animate them into clips with the selected clip model.
        key_dir = assets_dir / "keyframes"
        key_gen = generate_images(
            sdxl_turbo_model_id=img_id,
            prompts=prompts,
            out_dir=key_dir,
            max_images=max(1, int(video_settings.clips_per_video)),
        )
        keyframes = [g.path for g in key_gen]

        clip_dir = assets_dir / "clips"
        gen_clips = generate_clips(
            video_model_id=(clip_id or img_id),
            prompts=prompts,
            init_images=keyframes,
            out_dir=clip_dir,
            max_clips=max(1, int(video_settings.clips_per_video)),
            fps=int(video_settings.fps),
            seconds_per_clip=float(video_settings.clip_seconds),
        )
        clip_paths = [c.path for c in gen_clips]
        assemble_generated_clips_then_concat(
            ffmpeg_dir=paths.ffmpeg_dir,
            settings=video_settings,
            clips=clip_paths,
            voice_wav=voice_wav,
            captions_json=captions_json,
            out_final_mp4=out_final,
            out_assets_dir=assets_dir,
            background_music=music,
            branding=branding,
        )

    _write_video_folder(pkg=pkg, video_dir=video_dir, sources=sources, prompts=prompts)
    return video_dir


def main() -> None:
    if load_dotenv:
        load_dotenv()

    _single_instance_guard()

    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", action="store_true", help="Launch the desktop UI.")
    ap.add_argument("--cli", action="store_true", help="Run the CLI pipeline (default is UI).")
    ap.add_argument("--once", action="store_true", help="Run a single generation cycle and exit.")
    ap.add_argument("--interval-hours", type=float, default=4.0, help="Polling interval in hours.")
    ap.add_argument("--music", type=str, default="", help="Optional background music file path.")
    args = ap.parse_args()

    music = Path(args.music).resolve() if args.music else None

    # Default: launching main should bring up the UI (unless CLI mode requested).
    if args.ui or (not args.cli and not args.once):
        from UI.app import main as ui_main

        ui_main()
        return

    if args.once:
        app = AppSettings(topic_tags=[], background_music_path=str(music) if music else "")
        out = run_once(settings=app)
        if out:
            print(f"Created: {out}")
        else:
            print("No new items found.")
        return

    interval_s = max(60.0, args.interval_hours * 3600.0)
    while True:
        try:
            app = AppSettings(topic_tags=[], background_music_path=str(music) if music else "")
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

