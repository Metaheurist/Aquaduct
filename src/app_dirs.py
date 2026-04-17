"""
Installation directory + writable application data under ``.Aquaduct_data/``.

- **Development**: install dir = repo root (parent of ``src/``).
- **PyInstaller / frozen**: install dir = directory containing the executable (not ``_MEIPASS``).

Legacy layouts (data next to checkout / exe) are migrated once into ``.Aquaduct_data``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


APP_DATA_DIR_NAME = ".Aquaduct_data"

_migrated: bool = False


def installation_dir() -> Path:
    """Directory containing the app entrypoint: repo root (dev) or the executable folder (frozen)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def mark_path_hidden(path: Path) -> None:
    """Best-effort hide flag for files and folders (Windows + macOS). Linux: dot in name only."""
    try:
        resolved = path.resolve()
        if not resolved.exists():
            return
    except Exception:
        return

    if os.name == "nt":
        try:
            import ctypes

            FILE_ATTRIBUTE_HIDDEN = 0x2
            INVALID = 0xFFFFFFFF
            kernel32 = ctypes.windll.kernel32
            p = str(resolved)
            cur = kernel32.GetFileAttributesW(p)
            if cur == INVALID:
                return
            if not bool(cur & FILE_ATTRIBUTE_HIDDEN):
                kernel32.SetFileAttributesW(p, cur | FILE_ATTRIBUTE_HIDDEN)
        except Exception:
            return
    elif sys.platform == "darwin":
        try:
            subprocess.run(
                ["chflags", "hidden", str(resolved)],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except Exception:
            return


def _merge_directories(src: Path, dst: Path) -> None:
    """Move children from ``src`` into ``dst`` when names don't collide; recurse for dirs."""
    dst.mkdir(parents=True, exist_ok=True)
    for child in list(src.iterdir()):
        target = dst / child.name
        if target.exists():
            if child.is_dir() and target.is_dir():
                _merge_directories(child, target)
                try:
                    shutil.rmtree(child)
                except OSError:
                    pass
            continue
        try:
            shutil.move(str(child), str(target))
        except OSError:
            continue
    try:
        src.rmdir()
    except OSError:
        shutil.rmtree(src, ignore_errors=True)


def _migrate_legacy_into_app_data(install: Path, app_data: Path) -> None:
    # Settings file
    legacy_settings = install / "ui_settings.json"
    target_settings = app_data / "ui_settings.json"
    if legacy_settings.is_file():
        if not target_settings.exists():
            app_data.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(legacy_settings), str(target_settings))
            except OSError:
                pass
        else:
            try:
                legacy_settings.unlink()
            except OSError:
                pass

    # Top-level data dirs
    for name in ("data", "models", "runs", "videos"):
        src = install / name
        dst = app_data / name
        if not src.exists() or not src.is_dir():
            continue
        if not dst.exists():
            app_data.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(src), str(dst))
            except OSError:
                pass
        else:
            _merge_directories(src, dst)

    # Cache
    legacy_cache = install / ".cache"
    dst_cache = app_data / ".cache"
    if legacy_cache.exists() and legacy_cache.is_dir():
        if not dst_cache.exists():
            app_data.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(legacy_cache), str(dst_cache))
            except OSError:
                pass
        else:
            _merge_directories(legacy_cache, dst_cache)


def _run_migration_once() -> None:
    global _migrated
    if _migrated:
        return
    install = installation_dir()
    app_data = install / APP_DATA_DIR_NAME
    _migrate_legacy_into_app_data(install, app_data)
    _migrated = True


def application_data_dir() -> Path:
    """
    Ensures ``<install>/.Aquaduct_data`` exists, runs one-time migration from legacy
    repo-root / exe-adjacent paths, and marks the folder hidden where supported.
    """
    _run_migration_once()
    app_data = (installation_dir() / APP_DATA_DIR_NAME).resolve()
    app_data.mkdir(parents=True, exist_ok=True)
    mark_path_hidden(app_data)
    return app_data
