"""
One-time helper: migrate flat src/*.py into subpackages. Not run at runtime.
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# filename -> subpackage directory name
MOVE: dict[str, str] = {
    "app_dirs.py": "core",
    "config.py": "core",
    "model_manager.py": "models",
    "model_integrity_cache.py": "models",
    "hf_access.py": "models",
    "hf_transformers_imports.py": "models",
    "torch_dtypes.py": "models",
    "hardware.py": "models",
    "torch_install.py": "models",
    "pillow_compat.py": "models",
    "artist.py": "render",
    "clips.py": "render",
    "editor.py": "render",
    "ffmpeg_slideshow.py": "render",
    "utils_ffmpeg.py": "render",
    "frame_quality.py": "render",
    "branding_video.py": "render",
    "captions.py": "render",
    "facts_card.py": "render",
    "voice.py": "speech",
    "tts_text.py": "speech",
    "audio_fx.py": "speech",
    "elevenlabs_tts.py": "speech",
    "brain.py": "content",
    "storyboard.py": "content",
    "prompt_conditioning.py": "content",
    "character_presets.py": "content",
    "characters_store.py": "content",
    "personalities.py": "content",
    "personality_auto.py": "content",
    "crawler.py": "content",
    "topics.py": "content",
    "topic_discovery.py": "content",
    "factcheck.py": "content",
    "content_quality.py": "content",
    "firecrawl_news.py": "content",
    "ui_settings.py": "settings",
    "video_platform_presets.py": "settings",
    "effects_presets.py": "settings",
    "pipeline_control.py": "runtime",
    "preflight.py": "runtime",
    "tiktok_post.py": "platform",
    "tiktok_oauth_server.py": "platform",
    "youtube_upload.py": "platform",
    "upload_tasks.py": "platform",
    "fs_delete.py": "util",
    "utils_vram.py": "util",
    "network_status.py": "util",
    "repo_logs.py": "util",
    "cli_pip_display.py": "util",
    "single_instance.py": "util",
    "resource_sample.py": "util",
}

# Old module name (without src.) -> new dotted path under src
NEW_PATH: dict[str, str] = {k[:-3]: f"src.{v}.{k[:-3]}" for k, v in MOVE.items()}


def rewrite_imports(text: str) -> str:
    """Rewrite from src.OLD and from .OLD for moved modules."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        s = line
        # from src.X import / from src.X import (
        for old, new in sorted(NEW_PATH.items(), key=lambda x: -len(x[0])):
            if f"src.{old}" in s and old in NEW_PATH:
                s = s.replace(f"src.{old}", NEW_PATH[old].replace("src.", "src."))  # noqa
        for old, new in sorted(NEW_PATH.items(), key=lambda x: -len(x[0])):
            s = s.replace(f"from src.{old} ", f"from {NEW_PATH[old]} ")
            s = s.replace(f"import src.{old}", f"import {NEW_PATH[old]}")
        out.append(s)
    return "".join(out)


def main() -> None:
    for name, sub in MOVE.items():
        src_f = SRC / name
        if not src_f.exists():
            print("skip missing", src_f)
            continue
        dest_dir = SRC / sub
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "__init__.py").touch(exist_ok=True)
        dest = dest_dir / name
        shutil.move(str(src_f), str(dest))
        print("moved", name, "->", sub + "/")


if __name__ == "__main__":
    main()
