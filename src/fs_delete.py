"""
Best-effort recursive delete on Windows (readonly bits + transient lock retries).

Typical failures without this:
- WinError 5: readonly file/dir attributes
- WinError 32: another process still has a file open (often clears after a short delay)
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import time
from pathlib import Path


def _chmod_writable(path: str | os.PathLike[str]) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass


def _chmod_tree_writable(root: Path) -> None:
    try:
        _chmod_writable(root)
    except OSError:
        pass
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames:
            _chmod_writable(Path(dirpath) / name)
        for name in dirnames:
            _chmod_writable(Path(dirpath) / name)


def _rmtree_once(target: Path) -> None:
    if not target.exists():
        return

    if sys.version_info >= (3, 12):

        def onexc(func, path, exc):  # noqa: ARG001
            _chmod_writable(path)
            func(path)

        shutil.rmtree(target, onexc=onexc)
    else:

        def onerror(func, path, exc_info):  # noqa: ARG001
            _chmod_writable(path)
            func(path)

        shutil.rmtree(target, onerror=onerror)


def rmtree_robust(path: Path | str, *, attempts: int = 6, base_delay_s: float = 0.2) -> str | None:
    """
    Remove a directory tree. Returns None on success, or a short error string.
    """
    p = Path(path)
    if not p.exists():
        return None
    if not p.is_dir():
        try:
            _chmod_writable(p)
            p.unlink()
            return None
        except OSError as e:
            return f"Failed to delete file {p}: {e}"

    last: Exception | None = None
    for i in range(max(1, attempts)):
        try:
            _chmod_tree_writable(p)
            _rmtree_once(p)
            if not p.exists():
                return None
        except OSError as e:
            last = e
        except Exception as e:
            last = e
            break
        delay = base_delay_s * (1.35**i)
        time.sleep(delay)

    if p.exists():
        if last is not None:
            return f"Failed to delete {p}: {last}"
        return f"Failed to delete {p}: path still exists after retries"
    return None


def unlink_file(path: Path | str) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        _chmod_writable(p)
        p.unlink()
        return None
    except OSError as e:
        return f"Failed to delete {p}: {e}"
