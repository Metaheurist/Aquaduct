"""
Hugging Face Hub authentication helpers for background workers (LLM load, downloads).

The main window sets ``HF_TOKEN`` from saved settings at startup; workers re-apply when needed
so gated models work even if env was empty when the process started.
"""

from __future__ import annotations

import os


def ensure_hf_token_in_env(*, hf_token: str = "", hf_api_enabled: bool = True) -> None:
    """
    If ``HF_TOKEN`` / ``HUGGINGFACEHUB_API_TOKEN`` are unset, copy from saved UI settings.

    Mirrors ``MainWindow._apply_saved_hf_token_to_env`` so worker threads see the same token
    the UI would use for ``from_pretrained`` / ``hf_hub_download``.
    """
    if _env_has_hf_token():
        return
    if not hf_api_enabled:
        return
    t = (hf_token or "").strip()
    if not t:
        return
    os.environ["HF_TOKEN"] = t
    os.environ["HUGGINGFACEHUB_API_TOKEN"] = t


def _env_has_hf_token() -> bool:
    for key in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN"):
        if str(os.environ.get(key, "") or "").strip():
            return True
    return False


def humanize_hf_hub_error(exc: BaseException) -> str | None:
    """
    Return a short, actionable message for common Hub auth / gated-repo failures.
    """
    msg = f"{exc}"
    low = msg.lower()
    if (
        "401" in msg
        or "unauthorized" in low
        or "gated" in low
        or "restricted" in low
        or "cannot access gated repo" in low
        or "you are trying to access a gated repo" in low
    ):
        return (
            "Hugging Face blocked this download (401 / gated model).\n\n"
            "For models such as Llama:\n"
            "• On huggingface.co, open the model page and accept Meta’s license / access request.\n"
            "• API tab: turn on “Hugging Face API”, paste your Access Token (read), Save settings.\n"
            "• Or set HF_TOKEN in .env / environment before starting the app.\n\n"
            f"Details: {type(exc).__name__}: {exc}"
        )
    return None
