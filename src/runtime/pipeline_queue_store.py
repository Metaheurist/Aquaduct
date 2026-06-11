"""Persist the desktop pipeline FIFO across restarts."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.content.factcheck import _from_payload, _to_payload
from src.core.app_dirs import application_data_dir
from src.core.config import AppSettings
from src.settings.ui_settings import app_settings_from_dict

STORE_SCHEMA_VERSION = 1
STORE_FILENAME = "pipeline_queue.json"


def store_path() -> Path:
    return application_data_dir() / STORE_FILENAME


def _strip_ephemeral_settings_fields(d: dict[str, Any]) -> dict[str, Any]:
    out = dict(d)
    for k in (
        "resource_retry_resolution_scale",
        "resource_retry_frames_scale",
        "recovery_swapped_voice_model_id",
        "recovery_swapped_video_model_id",
        "recovery_swapped_image_model_id",
        "resume_partial_project_directory",
        "_force_cpu_diffusion",
    ):
        out.pop(k, None)
    return out


def _serialize_queue_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    kind = str(item.get("kind") or "pipeline").strip().lower()
    out: dict[str, Any] = {"kind": kind}
    if kind == "series_episode":
        out.update(
            {
                "series_slug": str(item.get("series_slug") or "").strip(),
                "episode_index": int(item.get("episode_index", 1) or 1),
                "episode_total": int(item.get("episode_total", 1) or 1),
                "is_first": bool(item.get("is_first", False)),
            }
        )
        return out
    settings = item.get("settings")
    if isinstance(settings, AppSettings):
        out["settings"] = _strip_ephemeral_settings_fields(asdict(settings))
    elif isinstance(settings, dict):
        out["settings"] = _strip_ephemeral_settings_fields(dict(settings))
    else:
        return None
    if kind == "pipeline":
        out["qty"] = int(item.get("qty", 1) or 1)
        return out
    if kind == "prebuilt":
        pkg = item.get("pkg")
        if pkg is not None:
            try:
                out["pkg"] = _to_payload(pkg)
            except Exception:
                return None
        out["sources"] = item.get("sources") if isinstance(item.get("sources"), list) else []
        out["prompts"] = item.get("prompts")
        return out
    if kind == "storyboard":
        out["prompts"] = item.get("prompts") if isinstance(item.get("prompts"), list) else []
        seeds = item.get("seeds")
        out["seeds"] = seeds if isinstance(seeds, list) else []
        return out
    return None


def _deserialize_queue_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "pipeline").strip().lower()
    if kind == "series_episode":
        slug = str(raw.get("series_slug") or "").strip()
        if not slug:
            return None
        return {
            "kind": "series_episode",
            "series_slug": slug,
            "episode_index": int(raw.get("episode_index", 1) or 1),
            "episode_total": int(raw.get("episode_total", 1) or 1),
            "is_first": bool(raw.get("is_first", False)),
        }
    settings_raw = raw.get("settings")
    if not isinstance(settings_raw, dict):
        return None
    settings = app_settings_from_dict(settings_raw)
    if kind == "pipeline":
        return {"kind": "pipeline", "settings": settings, "qty": int(raw.get("qty", 1) or 1)}
    if kind == "prebuilt":
        pkg_raw = raw.get("pkg")
        pkg = _from_payload(pkg_raw) if isinstance(pkg_raw, dict) else None
        return {
            "kind": "prebuilt",
            "settings": settings,
            "pkg": pkg,
            "sources": raw.get("sources") if isinstance(raw.get("sources"), list) else [],
            "prompts": raw.get("prompts"),
        }
    if kind == "storyboard":
        return {
            "kind": "storyboard",
            "settings": settings,
            "prompts": raw.get("prompts") if isinstance(raw.get("prompts"), list) else [],
            "seeds": raw.get("seeds") if isinstance(raw.get("seeds"), list) else [],
        }
    return None


def save_pipeline_queue(queue: list[dict[str, Any]]) -> bool:
    """Atomically persist the in-memory queue."""
    p = store_path()
    items: list[dict[str, Any]] = []
    for entry in queue or []:
        ser = _serialize_queue_item(entry)
        if ser is not None:
            items.append(ser)
    payload = json.dumps(
        {"schema_version": STORE_SCHEMA_VERSION, "items": items},
        indent=2,
        ensure_ascii=False,
    )
    tmp = p.parent / f".pipeline_queue_{os.getpid()}.tmp"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, p)
        return True
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def load_pipeline_queue() -> list[dict[str, Any]]:
    """Restore queue items from disk; returns ``[]`` when missing or invalid."""
    p = store_path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    if int(data.get("schema_version", 0) or 0) != STORE_SCHEMA_VERSION:
        return []
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in raw_items:
        item = _deserialize_queue_item(raw)
        if item is not None:
            out.append(item)
    return out


def clear_pipeline_queue() -> None:
    p = store_path()
    try:
        if p.is_file():
            p.unlink()
    except OSError:
        pass
