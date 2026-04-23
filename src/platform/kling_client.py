from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import time
from typing import Any

import requests

_DEFAULT_BASE = "https://api-singapore.klingai.com"
_POST_RETRY = frozenset({408, 425, 429, 500, 502, 503, 504})


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def kling_bearer_jwt(access_key: str, secret_key: str, *, lifetime_s: int = 30 * 60) -> str:
    """HS256 JWT for Kling Open Platform (iss = access key, exp/nbf). See Kling dev docs."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload: dict[str, int | str] = {
        "iss": access_key.strip(),
        "exp": now + max(60, int(lifetime_s)),
        "nbf": now - 5,
    }
    h = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    msg = f"{h}.{p}".encode("ascii")
    sig = hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"


class KlingRequestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _api_base() -> str:
    return (os.environ.get("KLING_API_BASE") or _DEFAULT_BASE).strip().rstrip("/")


def _headers(jwt: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}


def _map_err(status: int, body: str) -> str:
    if status in (401, 403):
        return "Kling API rejected the request — check KLING_ACCESS_KEY and KLING_SECRET_KEY."
    if status == 429:
        return "Kling API rate limited — retry later (free tier: ~66 credits/day, resets on a 24h window)."
    return f"Kling API HTTP {status}: {(body or '')[:400]}"


def _extract_video_url(obj: Any) -> str | None:
    """Best-effort: find an http(s) URL pointing at an MP4 in a query response tree."""
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("http") and (".mp4" in s.lower() or "video" in s.lower() or "/kling" in s.lower()):
            return s
        return None
    if isinstance(obj, dict):
        for k in ("url", "video_url", "resource", "resource_url", "download_url", "file_url", "mp4", "link"):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        for v in obj.values():
            u = _extract_video_url(v)
            if u:
                return u
    if isinstance(obj, list):
        for v in obj:
            u = _extract_video_url(v)
            if u:
                return u
    return None


def _sleep_backoff(attempt: int) -> None:
    time.sleep(min(6.0, 0.35 * (2**attempt) + random.random() * 0.1))


def kling_text_to_video_mp4_bytes(
    *,
    access_key: str,
    secret_key: str,
    prompt: str,
    model_name: str,
    end_seconds: float = 5.0,
    aspect_ratio: str = "9:16",
) -> bytes:
    """
    Create a text-to-video task, poll until complete, download MP4.

    `model_name` is the Kling model id (e.g. ``kling-v2-6`` / ``kling-v2-master``) from the Kling dev console.
    """
    p = (prompt or "").strip()
    if not p:
        raise KlingRequestError("Empty Kling text-to-video prompt.")
    m = (model_name or "").strip() or "kling-v2-master"
    T = max(1.0, min(10.0, float(end_seconds or 5.0)))
    dur = "5" if T <= 7.0 else "10"
    base = _api_base()
    jwt = kling_bearer_jwt(access_key, secret_key)
    create_path = f"{base}/v1/videos/text2video"
    nested: dict[str, Any] = {
        "input": {
            "model_name": m,
            "prompt": p[:2000],
            "duration": dur,
            "mode": "pro",
            "aspect_ratio": aspect_ratio,
        }
    }
    flat_body = {
        "model_name": m,
        "prompt": p[:2000],
        "duration": dur,
        "mode": "pro",
        "aspect_ratio": aspect_ratio,
    }

    def _do_post(payload: dict[str, Any]) -> requests.Response:
        last_exc: BaseException | None = None
        for attempt in range(4):
            try:
                resp = requests.post(create_path, headers=_headers(jwt), json=payload, timeout=120.0)
            except requests.RequestException as e:
                last_exc = e
                if attempt >= 3:
                    raise KlingRequestError(f"Kling network error: {e}") from e
                _sleep_backoff(attempt)
                continue
            if resp.status_code in _POST_RETRY and attempt < 3:
                _sleep_backoff(attempt)
                continue
            return resp
        raise KlingRequestError(f"Kling network error: {last_exc!r}")

    r = _do_post(nested)
    if r.status_code == 400:
        r = _do_post(flat_body)
    if r.status_code >= 400:
        raise KlingRequestError(_map_err(r.status_code, r.text), status_code=r.status_code)
    try:
        cj = r.json()
    except Exception as e:
        raise KlingRequestError("Kling create response was not JSON.") from e
    c0 = cj.get("code", 0)
    if c0 is not None and int(c0) != 0:
        raise KlingRequestError(str(cj.get("message") or cj)[:500])
    data = cj.get("data") or {}
    task_id = str((data.get("task_id") if isinstance(data, dict) else "") or "").strip()
    if not task_id:
        raise KlingRequestError("Kling did not return a task_id.")
    query = f"{base}/v1/videos/text2video/{task_id}"
    deadline = time.time() + 25 * 60
    while time.time() < deadline:
        time.sleep(1.5)
        try:
            pr = requests.get(query, headers=_headers(jwt), timeout=120.0)
        except requests.RequestException as e:
            raise KlingRequestError(f"Kling status poll failed: {e}") from e
        if pr.status_code >= 400:
            raise KlingRequestError(_map_err(pr.status_code, pr.text), status_code=pr.status_code)
        try:
            st = pr.json()
        except Exception as e:
            raise KlingRequestError("Kling status response was not JSON.") from e
        sc = st.get("code", 0)
        if sc is not None and int(sc) != 0:
            raise KlingRequestError(str(st.get("message") or st)[:500])
        sdata = st.get("data") or {}
        if not isinstance(sdata, dict):
            continue
        status = str(sdata.get("task_status") or sdata.get("status") or "").strip().lower()
        if status in ("failed", "error"):
            raise KlingRequestError(f"Kling job failed: {str(sdata.get('message') or status)[:400]}")
        if status in ("succeed", "success", "completed", "complete"):
            url = _extract_video_url(sdata)
            if not url:
                raise KlingRequestError("Kling completed but no video URL was found in the response.")
            dr = requests.get(url, timeout=180.0)
            dr.raise_for_status()
            return dr.content
    raise KlingRequestError("Kling job timed out while polling.")
