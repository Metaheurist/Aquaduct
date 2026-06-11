"""Lightweight coarse-grained checkpointing for resumed pipeline runs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from src.content.brain import VideoPackage
from src.content.factcheck import _from_payload, _to_payload

SCRIPT_PKG_NAME = "pipeline_script_package.json"


def checkpoint_path(assets_dir: Path) -> Path:
    return assets_dir / "run_checkpoint.json"


def fingerprint_for_settings(settings: Any) -> str:
    parts = "|".join(
        [
            str(getattr(settings, "llm_model_id", "") or ""),
            str(getattr(settings, "image_model_id", "") or ""),
            str(getattr(settings, "video_model_id", "") or ""),
            str(getattr(settings, "voice_model_id", "") or ""),
            str(getattr(settings, "media_mode", "video") or ""),
        ]
    ).lower()
    return parts


def script_package_path(assets_dir: Path) -> Path:
    return assets_dir / SCRIPT_PKG_NAME


def save_script_package(assets_dir: Path | None, pkg: VideoPackage | None) -> None:
    """Persist structured script/package JSON used to skip LLM on resume."""
    if assets_dir is None or pkg is None:
        return
    try:
        assets_dir.mkdir(parents=True, exist_ok=True)
        script_package_path(assets_dir).write_text(
            json.dumps(_to_payload(pkg), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def load_script_package(assets_dir: Path | None) -> VideoPackage | None:
    if assets_dir is None:
        return None
    p = script_package_path(assets_dir)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return _from_payload(raw)
    except Exception:
        return None


def load_checkpoint(assets_dir: Path | None, settings: Any) -> dict[str, Any] | None:
    if assets_dir is None:
        return None
    p = checkpoint_path(assets_dir)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    fp = fingerprint_for_settings(settings)
    if str(data.get("fingerprint") or "").lower().strip() != fp:
        return None
    return data


def stages_done(assets_dir: Path | None, settings: Any) -> set[str]:
    ck = load_checkpoint(assets_dir, settings)
    if not ck:
        return set()
    raw = ck.get("stages") or ck.get("stages_completed")
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if isinstance(x, str)}


def mark_stage_complete(assets_dir: Path | None, settings: Any, stage_id: str) -> None:
    if assets_dir is None:
        return
    fp = fingerprint_for_settings(settings)
    ck: dict[str, Any] = {"fingerprint": fp, "stages": sorted(stages_done(assets_dir, settings) | {str(stage_id)})}
    assets_dir.mkdir(parents=True, exist_ok=True)
    try:
        checkpoint_path(assets_dir).write_text(json.dumps(ck, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def clear_checkpoint(assets_dir: Path | None, settings: Any) -> None:
    if assets_dir is None:
        return
    p = checkpoint_path(assets_dir)
    try:
        if p.is_file():
            ck = load_checkpoint(assets_dir, settings)
            if ck:
                p.unlink()
    except Exception:
        pass


def merge_checkpoint_into_project(*, staging_assets: Path, project_assets: Path, settings: Any) -> None:
    """Union stage IDs from a per-run staging folder into the durable project assets folder."""
    try:
        merged = stages_done(staging_assets, settings) | stages_done(project_assets, settings)
        if not merged:
            return
        fp = fingerprint_for_settings(settings)
        project_assets.mkdir(parents=True, exist_ok=True)
        checkpoint_path(project_assets).write_text(
            json.dumps({"fingerprint": fp, "stages": sorted(merged)}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def copy_script_package_between_assets(staging_assets: Path, project_assets: Path) -> None:
    try:
        s = script_package_path(staging_assets)
        if s.is_file():
            project_assets.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, script_package_path(project_assets))
    except Exception:
        pass


def _resumable_candidate_mtime(project_dir: Path, settings: Any) -> float | None:
    """Return assets mtime when ``project_dir`` is a partial, resumable run; else ``None``."""
    try:
        if (project_dir / "final.mp4").is_file():
            return None
        assets = project_dir / "assets"
        if not assets.is_dir():
            return None
        ck = load_checkpoint(assets, settings)
        if not ck:
            return None
        stg = stages_done(assets, settings)
        if not stg or "done" in stg:
            return None
        if ("script_pkg" in stg or "script_llm" in stg) and not script_package_path(assets).is_file():
            return None
        return float(assets.stat().st_mtime)
    except Exception:
        return None


def _iter_video_project_dirs(root: Path) -> list[Path]:
    """
    Flat video folders under ``videos/`` plus nested series episodes ``videos/*/episode_*/``.
    """
    if not root.is_dir():
        return []
    out: list[Path] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        name = child.name.lower()
        if name.startswith("episode_"):
            out.append(child)
            continue
        # Series root: scan episode_* subfolders (newest episodes first within each series).
        episodes = sorted(
            (ep for ep in child.iterdir() if ep.is_dir() and ep.name.lower().startswith("episode_")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if episodes:
            out.extend(episodes)
        else:
            out.append(child)
    return out


def find_latest_resumable_video_project(root: Path, settings: Any, *, limit_scan: int = 200) -> Path | None:
    """
    Newest subdirectory under ``videos/`` (including ``videos/<series>/episode_*/``) that has a
    matching checkpoint without a terminal ``done`` stage and (when script milestones exist)
    ``pipeline_script_package.json``.
    """
    if not root.is_dir():
        return None
    candidates = sorted(_iter_video_project_dirs(root), key=lambda x: x.stat().st_mtime, reverse=True)
    best: tuple[float, Path] | None = None
    for child in candidates[:limit_scan]:
        mtime = _resumable_candidate_mtime(child, settings)
        if mtime is None:
            continue
        if best is None or mtime > best[0]:
            best = (mtime, child)
    return None if best is None else best[1]
