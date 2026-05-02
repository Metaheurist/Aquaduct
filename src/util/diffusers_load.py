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


def _is_protobuf_tokenizer_failure(exc: BaseException) -> bool:
    """Detect the specific transformers/tiktoken failure that means protobuf is missing
    (or transformers cached its absence at import time before pip install)."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        msg = str(cur)
        if (
            "SentencePieceExtractor requires the protobuf library" in msg
            or ("tiktoken" in msg.lower() and "spiece.model" in msg)
            or ("Error parsing line" in msg and "spiece.model" in msg)
        ):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def _protobuf_runtime_available() -> bool:
    try:
        import importlib

        importlib.import_module("google.protobuf")
        return True
    except Exception:
        return False


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

    def _do_attempts() -> T:
        nonlocal last_err
        for cur in attempts:
            try:
                return pipe_cls.from_pretrained(lp, **cur)
            except TypeError as e:
                last_err = e
                continue
            except Exception as e:
                if _is_protobuf_tokenizer_failure(e):
                    have_pb = _protobuf_runtime_available()
                    hint = (
                        "the running process was started before `protobuf` was installed; "
                        "transformers caches that check at import time. Restart the Aquaduct app."
                        if have_pb
                        else "install `protobuf` (e.g. `pip install \"protobuf>=4.25,<6\"`) and restart the app."
                    )
                    raise RuntimeError(
                        "Tokenizer load failed for "
                        f"'{lp}': transformers needs the `protobuf` library to convert "
                        "SentencePiece (.spiece.model) tokenizers (CogVideoX/T5-class). "
                        f"Fix: {hint}"
                    ) from e
                raise
        if last_err is not None:
            raise last_err
        raise RuntimeError("diffusers_from_pretrained: no attempts")

    try:
        from src.runtime.load_heartbeat import diffusion_load_watch

        with diffusion_load_watch(label=f"{hb_label}:{lp}"):
            return _do_attempts()
    except RuntimeError:
        raise
    except Exception:
        return _do_attempts()
