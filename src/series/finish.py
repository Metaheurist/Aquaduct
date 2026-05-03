"""Post-encode hooks for video series (register episode + bible)."""

from __future__ import annotations

from pathlib import Path

from src.core.config import AppSettings, Paths
from src.content.brain import VideoPackage
from src.series.context import SeriesContext
from src.series.recap import summarize_episode_for_series_bible
from src.series.store import register_episode


def finalize_series_episode_if_needed(
    *,
    paths: Paths,
    app: AppSettings,
    series_context: SeriesContext | None,
    video_dir: Path,
    pkg: VideoPackage,
    llm_model_id: str,
    llm_cuda_device_index: int | None,
) -> None:
    if series_context is None:
        return
    if str(getattr(app, "media_mode", "video") or "video").strip().lower() != "video":
        return
    script_path = video_dir / "script.txt"
    script_text = ""
    if script_path.is_file():
        try:
            script_text = script_path.read_text(encoding="utf-8")
        except OSError:
            script_text = ""
    if not (script_text or "").strip():
        script_text = pkg.narration_text()
    recap = summarize_episode_for_series_bible(
        app=app,
        script_text=script_text,
        episode_title=str(pkg.title or ""),
        llm_model_id=llm_model_id,
        llm_cuda_device_index=llm_cuda_device_index,
    )
    register_episode(
        paths,
        slug=series_context.series_slug,
        episode_index=int(series_context.episode_index),
        title=str(pkg.title or "").strip() or f"Episode {series_context.episode_index}",
        episode_project_dir=video_dir.resolve(),
        recap=recap,
    )
