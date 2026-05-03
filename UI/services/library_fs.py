"""Scan `.Aquaduct_data/videos/` and `runs/` for Library tab browsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.platform.upload_tasks import _read_title_from_video_dir


@dataclass(frozen=True)
class FinishedVideoFolder:
    path: Path
    title: str
    folder_name: str
    modified_ts: float
    final_bytes: int


@dataclass(frozen=True)
class RunWorkspaceFolder:
    path: Path
    modified_ts: float
    has_assets_dir: bool


def format_byte_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    x = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        x /= 1024.0
        if x < 1024.0 or unit == "TB":
            return f"{x:.1f} {unit}"
    return f"{n} B"


def scan_finished_videos(videos_dir: Path) -> list[FinishedVideoFolder]:
    """Subfolders of ``videos_dir`` that contain ``final.mp4``, newest first.

    Series layout: parent folder with ``series.json`` is scanned one level deep for
    ``episode_*`` subfolders that contain ``final.mp4``.
    """
    out: list[FinishedVideoFolder] = []
    try:
        if not videos_dir.is_dir():
            return out
        from src.series.store import SERIES_JSON_NAME, load_series_record

        _ep_dir_re = re.compile(r"^episode_(\d+)_", re.I)

        for p in videos_dir.iterdir():
            if not p.is_dir():
                continue
            if (p / SERIES_JSON_NAME).is_file():
                rec = load_series_record(p)
                series_label = (rec.name.strip() if rec else "") or p.name
                for ep in p.iterdir():
                    if not ep.is_dir():
                        continue
                    if not ep.name.startswith("episode_"):
                        continue
                    fin = ep / "final.mp4"
                    if not fin.is_file():
                        continue
                    ep_title = _read_title_from_video_dir(ep)
                    m_ep = _ep_dir_re.match(ep.name)
                    ep_n = int(m_ep.group(1)) if m_ep else 0
                    if ep_n:
                        title = f"Series: {series_label} · Ep {ep_n} — {ep_title}"
                    else:
                        title = f"Series: {series_label} · {ep_title}"
                    mtimes: list[float] = []
                    try:
                        mtimes.append(fin.stat().st_mtime)
                    except OSError:
                        pass
                    meta = ep / "meta.json"
                    if meta.is_file():
                        try:
                            mtimes.append(meta.stat().st_mtime)
                        except OSError:
                            pass
                    try:
                        mtimes.append(ep.stat().st_mtime)
                    except OSError:
                        pass
                    m = max(mtimes) if mtimes else 0.0
                    try:
                        b = int(fin.stat().st_size)
                    except OSError:
                        b = 0
                    out.append(
                        FinishedVideoFolder(
                            path=ep.resolve(),
                            title=title,
                            folder_name=ep.name,
                            modified_ts=m,
                            final_bytes=b,
                        )
                    )
                continue
            fin = p / "final.mp4"
            if not fin.is_file():
                continue
            title = _read_title_from_video_dir(p)
            mtimes: list[float] = []
            try:
                mtimes.append(fin.stat().st_mtime)
            except OSError:
                pass
            meta = p / "meta.json"
            if meta.is_file():
                try:
                    mtimes.append(meta.stat().st_mtime)
                except OSError:
                    pass
            try:
                mtimes.append(p.stat().st_mtime)
            except OSError:
                pass
            m = max(mtimes) if mtimes else 0.0
            try:
                b = int(fin.stat().st_size)
            except OSError:
                b = 0
            out.append(
                FinishedVideoFolder(
                    path=p.resolve(),
                    title=title,
                    folder_name=p.name,
                    modified_ts=m,
                    final_bytes=b,
                )
            )
    except OSError:
        return out
    out.sort(key=lambda e: e.modified_ts, reverse=True)
    return out


def scan_finished_pictures(pictures_dir: Path) -> list[FinishedVideoFolder]:
    """Subfolders of ``pictures_dir`` that contain ``final.png``, newest first (same row shape as videos)."""
    out: list[FinishedVideoFolder] = []
    try:
        if not pictures_dir.is_dir():
            return out
        for p in pictures_dir.iterdir():
            if not p.is_dir():
                continue
            fin = p / "final.png"
            if not fin.is_file():
                continue
            title = _read_title_from_video_dir(p)
            mtimes: list[float] = []
            try:
                mtimes.append(fin.stat().st_mtime)
            except OSError:
                pass
            meta = p / "meta.json"
            if meta.is_file():
                try:
                    mtimes.append(meta.stat().st_mtime)
                except OSError:
                    pass
            try:
                mtimes.append(p.stat().st_mtime)
            except OSError:
                pass
            m = max(mtimes) if mtimes else 0.0
            try:
                b = int(fin.stat().st_size)
            except OSError:
                b = 0
            out.append(
                FinishedVideoFolder(
                    path=p.resolve(),
                    title=title,
                    folder_name=p.name,
                    modified_ts=m,
                    final_bytes=b,
                )
            )
    except OSError:
        return out
    out.sort(key=lambda e: e.modified_ts, reverse=True)
    return out


def scan_run_workspaces(runs_dir: Path) -> list[RunWorkspaceFolder]:
    """All subfolders under ``runs_dir``, newest first."""
    out: list[RunWorkspaceFolder] = []
    try:
        if not runs_dir.is_dir():
            return out
        for p in runs_dir.iterdir():
            if not p.is_dir():
                continue
            try:
                m = p.stat().st_mtime
            except OSError:
                m = 0.0
            has_assets = (p / "assets").is_dir()
            out.append(
                RunWorkspaceFolder(
                    path=p.resolve(),
                    modified_ts=m,
                    has_assets_dir=has_assets,
                )
            )
    except OSError:
        return out
    out.sort(key=lambda e: e.modified_ts, reverse=True)
    return out
