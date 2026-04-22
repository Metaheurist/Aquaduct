from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

import requests

_POST_RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
_POST_MAX_ATTEMPTS = 4


def _sleep_backoff(attempt: int) -> None:
    base = min(8.0, 0.35 * (2**attempt))
    time.sleep(base + random.random() * 0.12)


class MagicHourRequestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}


def _map_err(status: int, body: str) -> str:
    if status in (401, 403):
        return "Magic Hour rejected the request — check MAGIC_HOUR_API_KEY."
    if status == 429:
        return "Magic Hour rate limited this account — retry later."
    return f"Magic Hour HTTP {status}: {(body or '')[:400]}"


def text_to_video_mp4_bytes(
    *,
    api_key: str,
    prompt: str,
    model: str = "default",
    end_seconds: float = 5.0,
    aspect_ratio: str = "9:16",
    resolution: str = "480p",
    timeout: float = 120.0,
) -> bytes:
    """Create a text-to-video job, poll until complete, download the first MP4."""
    if not (prompt or "").strip():
        raise MagicHourRequestError("Empty text-to-video prompt.")
    m = (model or "").strip() or "default"
    # Coerce duration to a sane value; free tier is often capped; API validates per model.
    dur = max(1.0, min(30.0, float(end_seconds)))
    create_url = "https://api.magichour.ai/v1/text-to-video"
    body: dict[str, Any] = {
        "end_seconds": dur,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "model": m,
        "style": {"prompt": (prompt or "").strip()[:2000]},
    }
    r: requests.Response | None = None
    last_exc: BaseException | None = None
    for attempt in range(_POST_MAX_ATTEMPTS):
        try:
            r = requests.post(create_url, headers=_headers(api_key), json=body, timeout=timeout)
        except requests.RequestException as e:
            last_exc = e
            if attempt >= _POST_MAX_ATTEMPTS - 1:
                raise MagicHourRequestError(f"Magic Hour network error: {e}") from e
            _sleep_backoff(attempt)
            continue
        if r.status_code in _POST_RETRY_STATUSES and attempt < _POST_MAX_ATTEMPTS - 1:
            _sleep_backoff(attempt)
            continue
        break
    if r is None:
        raise MagicHourRequestError(f"Magic Hour network error: {last_exc!r}")
    if r.status_code >= 400:
        raise MagicHourRequestError(_map_err(r.status_code, r.text), status_code=r.status_code)
    try:
        cj = r.json()
    except Exception as e:
        raise MagicHourRequestError("Magic Hour create response was not JSON.") from e
    project_id = str(cj.get("id") or "").strip()
    if not project_id:
        raise MagicHourRequestError("Magic Hour did not return a project id.")
    get_url = f"https://api.magichour.ai/v1/video-projects/{project_id}"
    deadline = time.time() + 25 * 60
    while time.time() < deadline:
        try:
            pr = requests.get(get_url, headers=_headers(api_key), timeout=timeout)
        except requests.RequestException as e:
            raise MagicHourRequestError(f"Magic Hour status poll failed: {e}") from e
        if pr.status_code >= 400:
            raise MagicHourRequestError(_map_err(pr.status_code, pr.text), status_code=pr.status_code)
        try:
            st = pr.json()
        except Exception as e:
            raise MagicHourRequestError("Magic Hour status response was not JSON.") from e
        status = str(st.get("status") or "").strip().lower()
        if status == "complete":
            dls = st.get("downloads")
            if not isinstance(dls, list) or not dls:
                raise MagicHourRequestError("Magic Hour completed but no downloads.")
            u = str((dls[0] or {}).get("url") or "").strip()
            if not u:
                raise MagicHourRequestError("Magic Hour download URL missing.")
            dr = requests.get(u, timeout=timeout * 2)
            dr.raise_for_status()
            return dr.content
        if status in ("error", "canceled"):
            err = st.get("error")
            if isinstance(err, dict):
                msg = str(err.get("message") or err)
            else:
                msg = str(err or status)
            raise MagicHourRequestError(f"Magic Hour job failed: {msg[:500]}")
        time.sleep(1.5)
    raise MagicHourRequestError("Magic Hour job timed out while polling.")
