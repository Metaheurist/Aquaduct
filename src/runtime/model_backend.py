from __future__ import annotations

import os
from typing import Literal

from src.core.config import ApiRoleConfig, AppSettings, ModelExecutionMode

Role = Literal["llm", "image", "video", "voice"]


def is_api_mode(settings: AppSettings | None) -> bool:
    return str(getattr(settings, "model_execution_mode", "local") or "local").strip().lower() == "api"


def effective_openai_api_key(settings: AppSettings | None) -> str:
    env = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if env:
        return env
    if settings is None:
        return ""
    return str(getattr(settings, "api_openai_key", "") or "").strip()


def effective_replicate_api_token(settings: AppSettings | None) -> str:
    for k in ("REPLICATE_API_TOKEN", "REPLICATE_API_KEY"):
        env = (os.environ.get(k) or "").strip()
        if env:
            return env
    if settings is None:
        return ""
    return str(getattr(settings, "api_replicate_token", "") or "").strip()


def _role_cfg(settings: AppSettings, role: Role) -> ApiRoleConfig:
    am = getattr(settings, "api_models", None)
    if am is None:
        return ApiRoleConfig()
    return getattr(am, role, ApiRoleConfig())


def provider_has_key(settings: AppSettings, provider: str) -> bool:
    p = str(provider or "").strip().lower()
    if not p:
        return False
    if p == "openai":
        return bool(effective_openai_api_key(settings))
    if p == "replicate":
        return bool(effective_replicate_api_token(settings))
    if p == "elevenlabs":
        from src.speech.elevenlabs_tts import effective_elevenlabs_api_key, elevenlabs_available_for_app

        return elevenlabs_available_for_app(settings) and bool(effective_elevenlabs_api_key(settings))
    return False


def role_filled(role_cfg: ApiRoleConfig) -> bool:
    return bool(str(role_cfg.provider or "").strip() and str(role_cfg.model or "").strip())


def assert_api_runtime_ready(settings: AppSettings) -> None:
    """Raise RuntimeError with user-facing text if API mode cannot run."""
    errs = api_preflight_errors(settings)
    if errs:
        raise RuntimeError("API mode is not ready:\n- " + "\n- ".join(errs))


def resolve_model_execution_mode(settings: AppSettings) -> ModelExecutionMode:
    m = str(getattr(settings, "model_execution_mode", "local") or "local").strip().lower()
    return "api" if m == "api" else "local"


def api_preflight_errors(settings: AppSettings) -> list[str]:
    """Return blocking error strings for API mode (empty if none)."""
    if not is_api_mode(settings):
        return []
    out: list[str] = []
    v = settings.video
    pro_on = bool(getattr(v, "pro_mode", False))
    slideshow = bool(getattr(v, "use_image_slideshow", True))
    for role, label in (("llm", "LLM (script)"), ("image", "Image"), ("voice", "Voice")):
        rc = _role_cfg(settings, role)  # type: ignore[arg-type]
        if not role_filled(rc):
            out.append(f"API mode: configure {label} provider and model (Generation APIs on the API tab).")
            continue
        prov = str(rc.provider or "").strip().lower()
        if not provider_has_key(settings, prov):
            out.append(f"API mode: missing API key for {label} provider “{prov}”.")
    if pro_on:
        vcfg = _role_cfg(settings, "video")
        if not role_filled(vcfg):
            out.append("API mode + Pro: configure Video API (Replicate model version id + token).")
        elif str(vcfg.provider or "").strip().lower() != "replicate":
            out.append("API mode + Pro: Video provider must be Replicate for cloud text-to-video.")
        elif not provider_has_key(settings, "replicate"):
            out.append("API mode + Pro: set REPLICATE_API_TOKEN or saved Replicate token.")
    elif not slideshow:
        out.append("API mode: enable slideshow (image stills) or use Pro mode with Replicate video — motion mode without local models is not supported.")
    return out
