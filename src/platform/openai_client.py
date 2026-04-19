from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

from src.core.config import AppSettings
from urllib.parse import urljoin

import requests


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
        try:
            r = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        except requests.RequestException as e:
            raise OpenAIRequestError(f"OpenAI network error: {e}") from e
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
        try:
            r = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        except requests.RequestException as e:
            raise OpenAIRequestError(f"OpenAI image network error: {e}") from e
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
        try:
            r = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        except requests.RequestException as e:
            raise OpenAIRequestError(f"OpenAI TTS network error: {e}") from e
        if r.status_code >= 400:
            raise OpenAIRequestError(_map_http_error(r.status_code, r.text), status_code=r.status_code)
        from pathlib import Path

        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)


def build_openai_client_from_settings(settings: AppSettings) -> OpenAIClient:
    from src.runtime.model_backend import effective_openai_api_key

    key = effective_openai_api_key(settings)
    llm = getattr(getattr(settings, "api_models", None), "llm", None)
    base = str(getattr(llm, "base_url", "") or "").strip() if llm else ""
    org = str(getattr(llm, "org_id", "") or "").strip() if llm else ""
    if not base:
        base = str(os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
    if not key:
        raise OpenAIRequestError("No OpenAI API key — set OPENAI_API_KEY or save a key under Generation APIs.")
    b = base.rstrip("/")
    if not b.endswith("/v1"):
        b = f"{b}/v1"
    return OpenAIClient(api_key=key, base_url=b + "/", organization=org or None)
