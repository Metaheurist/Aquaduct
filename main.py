from __future__ import annotations

import argparse
import json
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
from src.editor import assemble_microclips_then_concat
from src.voice import synthesize


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
    voice_id = app.voice_model_id.strip() or models.kokoro_id

    # Ensure base dirs exist
    paths.news_cache_dir.mkdir(parents=True, exist_ok=True)
    paths.runs_dir.mkdir(parents=True, exist_ok=True)
    paths.videos_dir.mkdir(parents=True, exist_ok=True)

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
    pkg = generate_script(
        model_id=llm_id,
        items=sources,
        topic_tags=app.topic_tags,
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
    img_dir = assets_dir / "images"
    gen = generate_images(
        sdxl_turbo_model_id=img_id,
        prompts=prompts,
        out_dir=img_dir,
        max_images=max(1, int(video_settings.images_per_video)),
    )
    image_paths = [g.path for g in gen]

    # Editor
    out_final = video_dir / "final.mp4"
    music = Path(app.background_music_path).resolve() if app.background_music_path else None
    assemble_microclips_then_concat(
        ffmpeg_dir=paths.ffmpeg_dir,
        settings=video_settings,
        images=image_paths,
        voice_wav=voice_wav,
        captions_json=captions_json,
        out_final_mp4=out_final,
        out_assets_dir=assets_dir,
        background_music=music,
    )

    _write_video_folder(pkg=pkg, video_dir=video_dir, sources=sources, prompts=prompts)
    return video_dir


def main() -> None:
    if load_dotenv:
        load_dotenv()

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

