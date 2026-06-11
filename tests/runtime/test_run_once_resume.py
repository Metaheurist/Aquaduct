"""Checkpoint resume helpers for partial pipeline runs."""

from __future__ import annotations

import json
from pathlib import Path

from src.content.factcheck import _to_payload
from src.content.brain import ScriptSegment, VideoPackage
from src.core.config import AppSettings
from src.runtime.run_checkpoint import (
    find_latest_resumable_video_project,
    mark_stage_complete,
    script_package_path,
)


def _write_partial_project(project_dir: Path, settings: AppSettings, *, stage: str = "script_llm") -> None:
    assets = project_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    pkg = VideoPackage(
        title="Resume test",
        description="",
        hashtags=[],
        hook="hook",
        segments=[ScriptSegment(narration="n", visual_prompt="v")],
        cta="",
    )
    script_package_path(assets).write_text(
        json.dumps(_to_payload(pkg), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    mark_stage_complete(assets, settings, stage)


def test_find_latest_resumable_flat_video_project(tmp_path: Path) -> None:
    settings = AppSettings(llm_model_id="llm-a", image_model_id="img-a")
    root = tmp_path / "videos"
    root.mkdir()
    older = root / "older_run"
    newer = root / "newer_run"
    _write_partial_project(older, settings)
    _write_partial_project(newer, settings, stage="voice")
    cand = find_latest_resumable_video_project(root, settings)
    assert cand is not None
    assert cand.name == "newer_run"


def test_find_latest_resumable_nested_series_episode(tmp_path: Path) -> None:
    settings = AppSettings(llm_model_id="llm-a", image_model_id="img-a")
    root = tmp_path / "videos"
    series = root / "my_series"
    ep1 = series / "episode_001_first"
    ep2 = series / "episode_002_second"
    _write_partial_project(ep1, settings, stage="script_llm")
    _write_partial_project(ep2, settings, stage="diffusion_image")
    cand = find_latest_resumable_video_project(root, settings)
    assert cand is not None
    assert cand == ep2


def test_find_latest_resumable_skips_done_and_final_mp4(tmp_path: Path) -> None:
    settings = AppSettings(llm_model_id="llm-a", image_model_id="img-a")
    root = tmp_path / "videos"
    done_dir = root / "finished"
    _write_partial_project(done_dir, settings)
    mark_stage_complete(done_dir / "assets", settings, "done")
    partial = root / "partial"
    _write_partial_project(partial, settings)
    (root / "has_final").mkdir()
    _write_partial_project(root / "has_final", settings)
    (root / "has_final" / "final.mp4").write_bytes(b"x" * 20_000)
    cand = find_latest_resumable_video_project(root, settings)
    assert cand is not None
    assert cand.name == "partial"
