from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent


def repo_root() -> Path:
    """Aquaduct repo root (parent of ``scripts/``)."""
    return _SCRIPT_DIR.parent


def ensure_repo_on_path(*, root: Path | None = None) -> Path:
    r = root or repo_root()
    if str(r) not in sys.path:
        sys.path.insert(0, str(r))
    return r


def load_repo_dotenv(*, root: Path | None = None) -> None:
    r = root or repo_root()
    try:
        from dotenv import load_dotenv

        load_dotenv(r / ".env", override=True)
    except Exception:
        pass


def confirm_destructive(*, prompt: str) -> bool:
    """True when the user types exactly ``YES`` (or EOF abort)."""
    try:
        return input(prompt).strip() == "YES"
    except EOFError:
        return False


def clear_path_robust(
    p: Path,
    *,
    label: str,
    skip_confirm: bool,
    recreate: bool = True,
    retry_rounds: int = 5,
) -> int | None:
    """
    Remove directory contents (best-effort). Returns ``None`` on success, else last error string.
    """
    from src.util.fs_delete import rmtree_robust

    print(f"Target ({label}): {p}")

    if not skip_confirm:
        if not confirm_destructive(prompt=f"Delete ALL contents of {label}? Type YES: "):
            print("Aborted.")
            return "aborted"

    last_err: str | None = None
    for attempt in range(1, retry_rounds + 1):
        err = rmtree_robust(p, attempts=10, base_delay_s=0.25)
        if err is None:
            if not p.exists():
                last_err = None
                break
            try:
                if not any(p.iterdir()):
                    last_err = None
                    break
            except OSError:
                last_err = None
                break
        last_err = str(err)
        print(f"Attempt {attempt}: {err}")
        time.sleep(1.5)

    if recreate:
        p.mkdir(parents=True, exist_ok=True)

    try:
        still = p.exists() and any(p.iterdir())
    except OSError:
        still = True
    if still:
        return last_err or "files remain"
    return None
