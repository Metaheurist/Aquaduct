from __future__ import annotations

import os
from typing import Literal

from src.core.config import ApiRoleConfig, AppSettings, ModelExecutionMode
from src.settings.api_model_catalog import uses_openai_chat_protocol_for_llm

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


def effective_llm_api_key(settings: AppSettings | None, provider: str) -> str:
    """Bearer for OpenAI or OpenAI-compatible LLM hosts (provider-specific env vars first, then saved OpenAI key field)."""
    from src.settings.api_model_catalog import provider_by_id

    p = str(provider or "").strip().lower() or "openai"
    spec = provider_by_id(p)
    if spec and spec.env_key_names:
        for name in spec.env_key_names:
            v = (os.environ.get(name) or "").strip()
            if v:
                return v
    return effective_openai_api_key(settings)


def effective_replicate_api_token(settings: AppSettings | None) -> str:
    for k in ("REPLICATE_API_TOKEN", "REPLICATE_API_KEY"):
        env = (os.environ.get(k) or "").strip()
        if env:
            return env
    if settings is None:
        return ""
    return str(getattr(settings, "api_replicate_token", "") or "").strip()


def effective_siliconflow_api_key(settings: AppSettings | None) -> str:
    v = (os.environ.get("SILICONFLOW_API_KEY") or "").strip()
    if v:
        return v
    return effective_openai_api_key(settings)


def effective_magic_hour_api_key(settings: AppSettings | None) -> str:
    for k in ("MAGIC_HOUR_API_KEY", "MAGICHOUR_API_KEY"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    if settings is None:
        return ""
    return ""


def effective_inworld_api_key(settings: AppSettings | None) -> str:
    v = (os.environ.get("INWORLD_API_KEY") or "").strip()
    if v:
        return v
    if settings is None:
        return ""
    return str(getattr(settings, "api_openai_key", "") or "").strip()


def effective_kling_access_key() -> str:
    return (os.environ.get("KLING_ACCESS_KEY") or os.environ.get("KLINGAI_ACCESS_KEY") or "").strip()


def effective_kling_secret_key() -> str:
    return (os.environ.get("KLING_SECRET_KEY") or os.environ.get("KLINGAI_SECRET_KEY") or "").strip()


def _role_cfg(settings: AppSettings, role: Role) -> ApiRoleConfig:
    am = getattr(settings, "api_models", None)
    if am is None:
        return ApiRoleConfig()
    return getattr(am, role, ApiRoleConfig())


def provider_has_key(settings: AppSettings, provider: str) -> bool:
    p = str(provider or "").strip().lower()
    if not p:
        return False
    if uses_openai_chat_protocol_for_llm(p):
        return bool(effective_llm_api_key(settings, p))
    if p == "replicate":
        return bool(effective_replicate_api_token(settings))
    if p == "siliconflow":
        return bool(effective_siliconflow_api_key(settings))
    if p == "magic_hour":
        return bool(effective_magic_hour_api_key(settings))
    if p == "inworld":
        return bool(effective_inworld_api_key(settings))
    if p == "kling":
        return bool(effective_kling_access_key() and effective_kling_secret_key())
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


def resolve_local_vs_api(settings: AppSettings | None) -> ModelExecutionMode:
    """Same as :func:`resolve_model_execution_mode` — plan-facing name for local vs API routing."""
    if settings is None:
        return "local"
    return resolve_model_execution_mode(settings)


def api_role_ready(settings: AppSettings, role: Role) -> bool:
    """True when API mode is on and the role has provider+model plus the required credential."""
    if not is_api_mode(settings):
        return False
    rc = _role_cfg(settings, role)
    if not role_filled(rc):
        return False
    prov = str(rc.provider or "").strip().lower()
    return provider_has_key(settings, prov)


def api_preflight_errors(settings: AppSettings) -> list[str]:
    """Return blocking error strings for API mode (empty if none)."""
    if not is_api_mode(settings):
        return []
    out: list[str] = []
    v = settings.video
    pro_on = bool(getattr(v, "pro_mode", False))
    slideshow = bool(getattr(v, "use_image_slideshow", True))
    mm = str(getattr(settings, "media_mode", "video") or "video").strip().lower()

    # Photo pipeline: script + still images only (no voice, no video clips).
    if mm == "photo":
        for role, label in (("llm", "LLM (script)"), ("image", "Image")):
            rc = _role_cfg(settings, role)  # type: ignore[arg-type]
            if not role_filled(rc):
                out.append(f"API mode: configure {label} provider and model (Generation APIs on the API tab).")
                continue
            prov = str(rc.provider or "").strip().lower()
            if not provider_has_key(settings, prov):
                out.append(f"API mode: missing API key for {label} provider “{prov}”.")
        return out

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
        vpr = str(vcfg.provider or "").strip().lower()
        if not role_filled(vcfg):
            out.append("API mode + Pro: configure Video API (provider + model / version id and token).")
        elif vpr not in ("replicate", "magic_hour", "kling"):
            out.append("API mode + Pro: Video provider must be Kling, Magic Hour, or Replicate (version id for Replicate).")
        elif vpr == "replicate" and not provider_has_key(settings, "replicate"):
            out.append("API mode + Pro: set REPLICATE_API_TOKEN or saved Replicate token.")
        elif vpr == "magic_hour" and not provider_has_key(settings, "magic_hour"):
            out.append("API mode + Pro: set MAGIC_HOUR_API_KEY for Magic Hour video.")
        elif vpr == "kling" and not provider_has_key(settings, "kling"):
            out.append("API mode + Pro: set KLING_ACCESS_KEY and KLING_SECRET_KEY for Kling (see Kling dev docs).")
    elif not slideshow:
        out.append("API mode: enable slideshow (image stills) or use Pro mode with Replicate video — motion mode without local models is not supported.")
    return out
