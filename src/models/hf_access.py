"""
Hugging Face Hub authentication helpers for background workers (LLM load, downloads).

The main window sets ``HF_TOKEN`` from saved settings at startup; workers re-apply when needed
so gated models work even if env was empty when the process started.
"""

from __future__ import annotations

import os


def ensure_hf_token_in_env(*, hf_token: str = "", hf_api_enabled: bool = True) -> None:
    """
    If ``HF_TOKEN`` / ``HUGGINGFACEHUB_API_TOKEN`` are unset, apply a non-empty saved token.

    Gated models need a token for downloads even when the HF API toggle is off.
    ``hf_api_enabled`` is kept for call-site compatibility but does **not** block injection.
    """
    _ = hf_api_enabled
    if _env_has_hf_token():
        return
    t = (hf_token or "").strip()
    if not t:
        try:
            from src.settings.ui_settings import load_settings

            t = str(getattr(load_settings(), "hf_token", "") or "").strip()
        except Exception:
            t = ""
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
    # Avoid matching unrelated text in LLM JSON previews (e.g. "401(k)", "HTTP 401" in a note).
    hub_auth = (
        ("401 client error" in low)
        or ("403 client error" in low)
        or ("cannot access gated repo" in low)
        or ("you are trying to access a gated repo" in low)
        or (
            ("repository not found" in low)
            and (("huggingface" in low) or ("hf.co" in low))
        )
        or (("invalid username or password" in low) and ("huggingface" in low))
        or (
            ("unauthorized" in low)
            and (("huggingface.co" in low) or ("hf.co" in low) or ("hub request" in low))
        )
    )
    if not hub_auth:
        return None
    return (
        "Hugging Face blocked this download (401 / gated model).\n\n"
        "For models such as Llama:\n"
        "- On huggingface.co, open the model page and accept Meta's license / access request.\n"
        '- API tab: turn on "Hugging Face API", paste your Access Token (read), Save settings.\n'
        "- Or set HF_TOKEN in .env / environment before starting the app.\n\n"
        f"Details: {type(exc).__name__}: {exc}"
    )
