from __future__ import annotations

from PyQt6.QtCore import QThread

from src.content.brain_api import (
    expand_custom_video_instructions_openai,
    generate_script_openai,
)
from src.content.firecrawl_news import resolve_firecrawl_api_key
from src.content.brain import expand_custom_video_instructions, generate_script
from src.core.config import AppSettings
from src.runtime.model_backend import is_api_mode
from src.runtime.oom_retry import is_oom_error
from src.runtime.pipeline_control import PipelineCancelled, PipelineRunControl


def raise_if_interrupted(
    worker: QThread,
    run_control: PipelineRunControl | None = None,
) -> None:
    """Honor ``requestInterruption()`` and cooperative pipeline cancel checkpoints."""
    if worker.isInterruptionRequested():
        raise PipelineCancelled()
    if run_control is not None:
        run_control.checkpoint()


def _failure_text_with_cuda_hints(exc: BaseException, tb: str) -> str:
    """Append VRAM/load hints when the traceback looks like CUDA OOM or related allocation failure."""
    tb_low = tb.lower()
    loading_weights = "load_state_dict" in tb_low or "model_loading_utils" in tb_low

    head = ""
    if isinstance(exc, MemoryError) and loading_weights:
        head = (
            "**MemoryError while loading model weights** - this usually means **Windows ran out of system RAM** "
            "(not only GPU VRAM) while diffusers/torch reads multi‑GB checkpoint shards. "
            "If the traceback ends inside `model_loading_utils.load_state_dict`, diffusers may be running an "
            "error‑recovery path that reads the whole shard.\n\n"
        )
    elif is_oom_error(exc):
        head = (
            "CUDA / VRAM memory error - the GPU ran out of memory or an allocator refused the request.\n\n"
        )

    msg = head + f"{exc}\n\n{tb}"

    if isinstance(exc, MemoryError) and loading_weights:
        msg += (
            "\n\n---\nTip (RAM / checkpoints): Close heavy apps (browser, other ML tools), restart Aquaduct, "
            "then retry. **Wan 2.2 14B** often needs **much more free RAM than 12 GiB VRAM suggests** - "
            "try **THUDM/CogVideoX-5b** or another lighter Video repo if loads keep failing after CPU offload. "
            "Ensure checkpoints are fully downloaded (HF snapshot / git‑LFS pointers break loads differently).\n"
        )
    elif is_oom_error(exc):
        msg += (
            "\n\n---\nTip (VRAM): Large local T2V models (e.g. Wan 2.2 14B) often need "
            "**CPU offload** on ~12 GiB GPUs - Model tab → Video → quantization → CPU offload - "
            "or pick a lighter video repo. See docs/reference/inference_profiles.md (Troubleshooting).\n"
        )
    return msg


def _reraise_system_interrupt(exc: BaseException) -> None:
    """Let Ctrl+C / sys.exit propagate from worker threads; handle everything else via failed.emit."""
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        raise exc


def _expand_brief_unified(
    *,
    app: AppSettings,
    model_id: str,
    raw_instructions: str,
    video_format: str,
    personality_id: str,
    character_context: str | None,
    on_llm_task,
    try_llm_4bit: bool,
):
    if is_api_mode(app):
        return expand_custom_video_instructions_openai(
            settings=app,
            raw_instructions=raw_instructions,
            video_format=video_format,
            personality_id=personality_id,
            on_llm_task=on_llm_task,
        )
    from src.util.cuda_device_policy import resolve_llm_cuda_device_index

    return expand_custom_video_instructions(
        model_id=model_id,
        raw_instructions=raw_instructions,
        video_format=video_format,
        personality_id=personality_id,
        character_context=character_context,
        on_llm_task=on_llm_task,
        try_llm_4bit=try_llm_4bit,
        llm_cuda_device_index=resolve_llm_cuda_device_index(app),
        inference_settings=app,
    )


def _generate_script_unified(
    *,
    app: AppSettings,
    model_id: str,
    on_llm_task,
    try_llm_4bit: bool,
    **kw,
):
    if is_api_mode(app):
        return generate_script_openai(settings=app, on_llm_task=on_llm_task, **kw)
    from src.util.cuda_device_policy import resolve_llm_cuda_device_index

    return generate_script(
        model_id=model_id,
        on_llm_task=on_llm_task,
        try_llm_4bit=try_llm_4bit,
        llm_cuda_device_index=resolve_llm_cuda_device_index(app),
        **{**kw, "inference_settings": app},
    )


def _firecrawl_kwargs(app: AppSettings) -> dict:
    return dict(
        firecrawl_enabled=bool(getattr(app, "firecrawl_enabled", False)),
        firecrawl_api_key=str(getattr(app, "firecrawl_api_key", "") or ""),
    )


def firecrawl_search_ready(app: AppSettings) -> bool:
    """True when Firecrawl is enabled and an API key is available (UI or FIRECRAWL_API_KEY)."""
    if not bool(getattr(app, "firecrawl_enabled", False)):
        return False
    return bool(resolve_firecrawl_api_key(str(getattr(app, "firecrawl_api_key", "") or "")))


def _fmt_bytes(n: int | float | None) -> str:
    if n is None:
        return "-"
    try:
        x = float(n)
    except Exception:
        return "-"
    if x < 0:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    u = 0
    while x >= 1024.0 and u < len(units) - 1:
        x /= 1024.0
        u += 1
    if u == 0:
        return f"{int(x)} {units[u]}"
    return f"{x:.1f} {units[u]}"
