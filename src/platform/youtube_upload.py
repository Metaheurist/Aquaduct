"""
YouTube Data API v3 — OAuth 2.0 (desktop) + resumable upload.

Enable the YouTube Data API v3 on your Google Cloud project and create an
OAuth 2.0 Client ID (Desktop). See docs/integrations/youtube.md.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def default_youtube_redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}/callback/"


def build_authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scope: str = YOUTUBE_UPLOAD_SCOPE,
) -> str:
    q = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )
    return f"{GOOGLE_AUTH}?{q}"


def _form_post(url: str, data: dict[str, str], timeout_s: int = 60) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw) if raw else {}
        except Exception:
            raise ValueError(raw or str(e)) from e
    return json.loads(raw) if raw else {}


def exchange_authorization_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    return _form_post(
        GOOGLE_TOKEN,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )


def refresh_access_token(*, client_id: str, client_secret: str, refresh_token: str) -> dict[str, Any]:
    return _form_post(
        GOOGLE_TOKEN,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )


def parse_token_response(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("error"):
        desc = str(payload.get("error_description") or payload.get("error") or "oauth_error")
        raise ValueError(desc)
    access = str(payload.get("access_token") or "")
    if not access:
        raise ValueError("No access_token in Google token response")
    return {
        "access_token": access,
        "refresh_token": str(payload.get("refresh_token") or ""),
        "expires_in": int(payload.get("expires_in") or 3600),
    }


def ensure_youtube_access_token(
    client_id: str,
    client_secret: str,
    access_token: str,
    refresh_token: str,
    expires_at: float,
) -> tuple[str, str, float]:
    now = time.time()
    if access_token and expires_at > now + 120:
        return access_token, refresh_token, expires_at
    if not refresh_token:
        raise ValueError("Not connected to YouTube — use Connect in the API tab first.")
    out = refresh_access_token(client_id=client_id, client_secret=client_secret, refresh_token=refresh_token)
    p = parse_token_response(out)
    exp = now + float(p["expires_in"])
    return p["access_token"], p.get("refresh_token") or refresh_token, exp


def upload_mp4_resumable(
    access_token: str,
    video_path: Path,
    *,
    title: str,
    description: str,
    privacy_status: str = "private",
    category_id: str = "24",
    self_declared_made_for_kids: bool = False,
) -> str:
    """
    Resumable upload per YouTube Data API. Returns the new video id.
    For Shorts, use vertical video; description often includes #Shorts.
    """
    video_path = video_path.resolve()
    raw = video_path.read_bytes()
    size = len(raw)
    if size <= 0:
        raise ValueError("Video file is empty")

    meta = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "categoryId": str(category_id),
        },
        "status": {
            "privacyStatus": privacy_status if privacy_status in ("public", "unlisted", "private") else "private",
            "selfDeclaredMadeForKids": bool(self_declared_made_for_kids),
        },
    }
    body_json = json.dumps(meta).encode("utf-8")
    qs = urllib.parse.urlencode({"uploadType": "resumable", "part": "snippet,status"})
    url = f"{YOUTUBE_UPLOAD}?{qs}"
    req = urllib.request.Request(
        url,
        data=body_json,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "Content-Length": str(len(body_json)),
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            loc = resp.headers.get("Location") or resp.headers.get("location")
            status = int(resp.status)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"YouTube init failed ({e.code}): {err_body}") from e

    if status not in (200, 201) or not loc:
        raise ValueError("YouTube resumable init did not return a Location header")

    put_req = urllib.request.Request(
        str(loc).strip(),
        data=raw,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "video/mp4",
            "Content-Length": str(size),
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(put_req, timeout=600) as resp2:
            out_raw = resp2.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"YouTube upload PUT failed ({e.code}): {err_body}") from e

    try:
        video_blob = json.loads(out_raw) if out_raw else {}
    except Exception:
        video_blob = {}
    vid = ""
    if isinstance(video_blob, dict):
        vid = str(video_blob.get("id") or "")
    if not vid:
        raise ValueError(f"YouTube upload finished but no video id in response: {out_raw[:800]}")
    return vid


def build_shorts_title_description(
    video_dir: Path,
    *,
    add_shorts_hashtag: bool,
) -> tuple[str, str]:
    """Reuse meta.json + hashtags.txt; optionally ensure #Shorts for discovery."""
            from src.platform.tiktok_post import build_caption_package

    title, cap = build_caption_package(video_dir)
    if add_shorts_hashtag:
        if "#shorts" not in cap.lower() and "#short" not in cap.lower():
            cap = (cap + " #Shorts").strip()
        if "shorts" not in title.lower():
            title = (title + " #Shorts").strip()[:100]
    return title[:100], cap[:5000]
