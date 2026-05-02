from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def diffusers_mmap_kw_for_pretrained() -> dict[str, Any]:
    """Extra kwargs for diffusers ``*.from_pretrained`` when env asks."""
    if _env_truthy("AQUADUCT_DIFFUSERS_DISABLE_MMAP"):
        return {"disable_mmap": True}
    return {}


def diffusers_from_pretrained(pipe_cls: Callable[..., T], load_path: str | Path, **kwargs: Any) -> T:
    """
    Call ``pipe_cls.from_pretrained(load_path, **kwargs)`` with optional ``disable_mmap=True``
    when ``AQUADUCT_DIFFUSERS_DISABLE_MMAP`` is set.

    Drops ``disable_mmap`` and/or ``low_cpu_mem_usage`` on ``TypeError`` for older diffusers.
    """
    lp: str | Path = load_path if isinstance(load_path, Path) else str(load_path)
    base = dict(kwargs)
    base.update(diffusers_mmap_kw_for_pretrained())

    variants = [
        dict(base),
        {k: v for k, v in base.items() if k != "disable_mmap"},
        {k: v for k, v in base.items() if k != "low_cpu_mem_usage"},
        {k: v for k, v in base.items() if k not in ("disable_mmap", "low_cpu_mem_usage")},
    ]
    attempts: list[dict[str, Any]] = []
    prev: dict[str, Any] | None = None
    for cur in variants:
        if prev is not None and cur == prev:
            continue
        attempts.append(cur)
        prev = cur

    last_err: BaseException | None = None
    hb_label = getattr(pipe_cls, "__name__", "diffusers_pipeline")
    try:
        from src.runtime.load_heartbeat import diffusion_load_watch

        with diffusion_load_watch(label=f"{hb_label}:{lp}"):
            for cur in attempts:
                try:
                    return pipe_cls.from_pretrained(lp, **cur)
                except TypeError as e:
                    last_err = e
                    continue
    except Exception:
        for cur in attempts:
            try:
                return pipe_cls.from_pretrained(lp, **cur)
            except TypeError as e:
                last_err = e
                continue
    if last_err is not None:
        raise last_err
    raise RuntimeError("diffusers_from_pretrained: no attempts")
