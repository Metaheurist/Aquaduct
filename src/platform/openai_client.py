from __future__ import annotations

import base64
import os
import random
import time
from dataclasses import dataclass
from typing import Any

from src.core.config import AppSettings
from urllib.parse import urljoin

import requests

_POST_RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
_POST_MAX_ATTEMPTS = 4


def _sleep_backoff(attempt: int) -> None:
    base = min(8.0, 0.35 * (2**attempt))
    time.sleep(base + random.random() * 0.12)


class OpenAIRequestError(RuntimeError):
    """User-safe OpenAI HTTP failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _scrub_for_logs(headers: dict[str, str]) -> dict[str, str]:
    out = dict(headers)
    if "Authorization" in out:
        out["Authorization"] = "Bearer ***"
    return out


def _map_http_error(status: int, body: str) -> str:
    if status in (401, 403):
        return "OpenAI rejected the request — check your API key (401/403)."
    if status == 429:
        return "OpenAI rate limited this account — retry later (429)."
    if status >= 500:
        return f"OpenAI server error ({status}). Try again later."
    snippet = (body or "")[:400].replace("\n", " ")
    return f"OpenAI HTTP {status}: {snippet}"


@dataclass
class OpenAIClient:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    organization: str | None = None
    timeout: float = 120.0

    def _headers(self) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
        }
        if (self.organization or "").strip():
            h["OpenAI-Organization"] = str(self.organization).strip()
        return h

    def _post_json(self, url: str, payload: dict[str, Any], *, err_prefix: str) -> requests.Response:
        """POST with limited retries on transient HTTP statuses and connection errors."""
        last_exc: BaseException | None = None
        for attempt in range(_POST_MAX_ATTEMPTS):
            try:
                r = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
            except requests.RequestException as e:
                last_exc = e
                if attempt >= _POST_MAX_ATTEMPTS - 1:
                    raise OpenAIRequestError(f"{err_prefix}OpenAI network error: {e}") from e
                _sleep_backoff(attempt)
                continue
            if r.status_code in _POST_RETRY_STATUSES and attempt < _POST_MAX_ATTEMPTS - 1:
                _sleep_backoff(attempt)
                continue
            return r
        raise OpenAIRequestError(f"{err_prefix}OpenAI network error: {last_exc!r}")

    def chat_completion_text(
        self,
        *,
        model: str,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> str:
        url = urljoin(self.base_url.rstrip("/") + "/", "chat/completions")
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        r = self._post_json(url, payload, err_prefix="")
        if r.status_code >= 400:
            try:
                from debug import dprint

                hdrs = dict(r.request.headers) if getattr(r, "request", None) is not None else {}
                dprint("openai", "chat http error", int(r.status_code), str(_scrub_for_logs(hdrs)))
            except Exception:
                pass
            raise OpenAIRequestError(_map_http_error(r.status_code, r.text), status_code=r.status_code)
        try:
            data = r.json()
            return str(data["choices"][0]["message"]["content"] or "")
        except Exception as e:
            raise OpenAIRequestError("OpenAI returned an unexpected response shape.") from e

    def download_image_png(self, *, model: str, prompt: str, size: str = "1024x1792") -> bytes:
        """Returns PNG bytes (DALL·E)."""
        url = urljoin(self.base_url.rstrip("/") + "/", "images/generations")
        payload = {"model": model, "prompt": prompt, "size": size, "response_format": "b64_json", "n": 1}
        r = self._post_json(url, payload, err_prefix="OpenAI image ")
        if r.status_code >= 400:
            try:
                from debug import dprint

                hdrs = dict(r.request.headers) if getattr(r, "request", None) is not None else {}
                dprint("openai", "image http error", int(r.status_code), str(_scrub_for_logs(hdrs)))
            except Exception:
                pass
            raise OpenAIRequestError(_map_http_error(r.status_code, r.text), status_code=r.status_code)
        try:
            data = r.json()
            b64 = data["data"][0]["b64_json"]
            return base64.b64decode(b64)
        except Exception as e:
            raise OpenAIRequestError("OpenAI image response missing base64 payload.") from e

    def speech_to_file(self, *, model: str, text: str, voice: str, out_path: str) -> None:
        url = urljoin(self.base_url.rstrip("/") + "/", "audio/speech")
        payload = {"model": model, "input": text, "voice": voice}
        r = self._post_json(url, payload, err_prefix="OpenAI TTS ")
        if r.status_code >= 400:
            raise OpenAIRequestError(_map_http_error(r.status_code, r.text), status_code=r.status_code)
        from pathlib import Path

        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)


def build_openai_client_from_settings(settings: AppSettings) -> OpenAIClient:
    from src.runtime.model_backend import effective_llm_api_key
    from src.settings.api_model_catalog import default_openai_compatible_base_url_for_llm

    llm = getattr(getattr(settings, "api_models", None), "llm", None)
    prov = str(getattr(llm, "provider", "") or "").strip().lower() if llm else "openai"
    key = effective_llm_api_key(settings, prov or "openai")
    base = str(getattr(llm, "base_url", "") or "").strip() if llm else ""
    org = str(getattr(llm, "org_id", "") or "").strip() if llm else ""
    if not base:
        base = str(os.environ.get("OPENAI_BASE_URL") or "").strip()
    if not base:
        cand = default_openai_compatible_base_url_for_llm(prov)
        if cand:
            base = cand.strip()
    if not base:
        base = "https://api.openai.com/v1"
    if not key:
        raise OpenAIRequestError(
            "No API key — set the provider’s env variable (e.g. OPENAI_API_KEY, GROQ_API_KEY) "
            "or save a key under Generation APIs (OpenAI / compatible LLM key field)."
        )
    b = base.rstrip("/")
    if not b.endswith("/v1"):
        b = f"{b}/v1"
    return OpenAIClient(api_key=key, base_url=b + "/", organization=org or None)
