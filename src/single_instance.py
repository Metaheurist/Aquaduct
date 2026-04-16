"""
Ensure only one app instance (CLI or UI).

Windows: named mutex in the *Local* namespace (no admin; Global\\ often fails without elevation).
If mutex creation fails, fall back to a non-blocking lock file under `.cache/`.

Keeps mutex handle / lock file open for the process lifetime so the lock is not released by GC.
"""

from __future__ import annotations

import os
from typing import Any

# Hold handles so they are not closed until process exit.
_mutex_handle: Any = None
_lock_fp: Any = None
_installed: bool = False

ERROR_ALREADY_EXISTS = 183


def single_instance_guard(name: str = "Aquaduct") -> None:
    global _mutex_handle, _lock_fp, _installed

    if _installed:
        return

    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetLastError(0)
            # Local\\ works without admin; Global\\ can fail with ERROR_ACCESS_DENIED (5).
            mutex_name = f"Local\\{name}SingleInstance"
            mutex = kernel32.CreateMutexW(None, ctypes.c_bool(True), mutex_name)
            last_err = int(kernel32.GetLastError())
            if mutex:
                if last_err == ERROR_ALREADY_EXISTS:
                    raise SystemExit(f"{name} is already running.")
                _mutex_handle = mutex
                _installed = True
                return
        except SystemExit:
            raise
        except Exception:
            pass

    try:
        import msvcrt  # type: ignore
    except Exception:
        msvcrt = None  # type: ignore

    from src.config import get_paths

    paths = get_paths()
    lock_path = paths.cache_dir / f"{name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    _lock_fp = open(lock_path, "a+", encoding="utf-8")
    try:
        if msvcrt:
            msvcrt.locking(_lock_fp.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # type: ignore

            fcntl.flock(_lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        try:
            _lock_fp.close()
        except Exception:
            pass
        _lock_fp = None
        raise SystemExit(f"{name} is already running.")

    _installed = True
