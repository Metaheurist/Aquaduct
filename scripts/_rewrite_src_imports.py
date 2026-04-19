"""One-off: rewrite flat `src.<name>` imports to subpackage paths. Run from repo root."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Old flat module name -> new path under src (without src. prefix)
MAP: list[tuple[str, str]] = [
    ("model_integrity_cache", "models.model_integrity_cache"),
    ("hf_transformers_imports", "models.hf_transformers_imports"),
    ("video_platform_presets", "settings.video_platform_presets"),
    ("prompt_conditioning", "content.prompt_conditioning"),
    ("character_presets", "content.character_presets"),
    ("characters_store", "content.characters_store"),
    ("personality_auto", "content.personality_auto"),
    ("topic_discovery", "content.topic_discovery"),
    ("content_quality", "content.content_quality"),
    ("firecrawl_news", "content.firecrawl_news"),
    ("ffmpeg_slideshow", "render.ffmpeg_slideshow"),
    ("branding_video", "render.branding_video"),
    ("frame_quality", "render.frame_quality"),
    ("utils_ffmpeg", "render.utils_ffmpeg"),
    ("elevenlabs_tts", "speech.elevenlabs_tts"),
    ("cli_pip_display", "util.cli_pip_display"),
    ("tiktok_oauth_server", "platform.tiktok_oauth_server"),
    ("pipeline_control", "runtime.pipeline_control"),
    ("resource_sample", "util.resource_sample"),
    ("single_instance", "util.single_instance"),
    ("network_status", "util.network_status"),
    ("model_manager", "models.model_manager"),
    ("effects_presets", "settings.effects_presets"),
    ("youtube_upload", "platform.youtube_upload"),
    ("upload_tasks", "platform.upload_tasks"),
    ("torch_transformers_imports", "models.hf_transformers_imports"),
    ("ui_settings", "settings.ui_settings"),
    ("utils_vram", "util.utils_vram"),
    ("repo_logs", "util.repo_logs"),
    ("fs_delete", "util.fs_delete"),
    ("preflight", "runtime.preflight"),
    ("tiktok_post", "platform.tiktok_post"),
    ("torch_install", "models.torch_install"),
    ("torch_dtypes", "models.torch_dtypes"),
    ("hf_access", "models.hf_access"),
    ("hardware", "models.hardware"),
    ("pillow_compat", "models.pillow_compat"),
    ("app_dirs", "core.app_dirs"),
    ("storyboard", "content.storyboard"),
    ("personalities", "content.personalities"),
    ("tts_text", "speech.tts_text"),
    ("audio_fx", "speech.audio_fx"),
    ("topics", "content.topics"),
    ("crawler", "content.crawler"),
    ("factcheck", "content.factcheck"),
    ("config", "core.config"),
    ("artist", "render.artist"),
    ("clips", "render.clips"),
    ("editor", "render.editor"),
    ("captions", "render.captions"),
    ("facts_card", "render.facts_card"),
    ("voice", "speech.voice"),
    ("brain", "content.brain"),
]


def rewrite_text(text: str) -> str:
    for old, new in MAP:
        # from src.old import / from src.old.sub
        text = re.sub(
            rf"\bfrom src\.{re.escape(old)}\b",
            f"from src.{new}",
            text,
        )
        # import src.old / import src.old as
        text = re.sub(
            rf"\bimport src\.{re.escape(old)}\b",
            f"import src.{new}",
            text,
        )
    return text


def main() -> None:
    skip = {"_rewrite_src_imports.py", "_migrate_src_layout.py"}
    for path in REPO.rglob("*.py"):
        if path.name in skip:
            continue
        rel = path.relative_to(REPO)
        if "site-packages" in rel.parts or ".venv" in rel.parts:
            continue
        raw = path.read_text(encoding="utf-8")
        out = rewrite_text(raw)
        if out != raw:
            path.write_text(out, encoding="utf-8", newline="\n")
            print("updated", rel)


if __name__ == "__main__":
    main()
