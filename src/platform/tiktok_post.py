"""
TikTok Content Posting API (OAuth + inbox video upload).

Requires a TikTok developer app, registered redirect URI, and user OAuth.
See docs/tiktok.md for setup.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"


def default_redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}/callback/"


def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for TikTok desktop PKCE (SHA256 hex challenge)."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    verifier = "".join(secrets.choice(alphabet) for _ in range(64))
    challenge = hashlib.sha256(verifier.encode("utf-8")).hexdigest()
    return verifier, challenge


def build_authorize_url(
    *,
    client_key: str,
    redirect_uri: str,
    state: str,
    scopes: list[str],
    code_challenge: str,
) -> str:
    q = urllib.parse.urlencode(
        {
            "client_key": client_key,
            "response_type": "code",
            "scope": ",".join(scopes),
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTH_URL}?{q}"


def _form_post(url: str, data: dict[str, str], timeout_s: int = 60) -> dict[str, Any]:
    import json

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
    client_key: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    data = {
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    return _form_post(TOKEN_URL, data)


def refresh_access_token(
    *,
    client_key: str,
    client_secret: str,
    refresh_token: str,
) -> dict[str, Any]:
    data = {
        "client_key": client_key,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    return _form_post(TOKEN_URL, data)


def parse_token_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize token response; raises ValueError on OAuth error shape."""
    if payload.get("error"):
        desc = str(payload.get("error_description") or payload.get("error") or "oauth_error")
        raise ValueError(desc)
    access = str(payload.get("access_token") or "")
    if not access:
        raise ValueError("No access_token in TikTok response")
    return {
        "access_token": access,
        "refresh_token": str(payload.get("refresh_token") or ""),
        "open_id": str(payload.get("open_id") or ""),
        "expires_in": int(payload.get("expires_in") or 86400),
        "scope": str(payload.get("scope") or ""),
    }


def ensure_fresh_access_token(
    client_key: str,
    client_secret: str,
    access_token: str,
    refresh_token: str,
    expires_at: float,
) -> tuple[str, str, float]:
    """
    Return (access_token, refresh_token, new_expires_at).
    Refreshes if missing or expiring within 120s.
    """
    now = time.time()
    if access_token and expires_at > now + 120:
        return access_token, refresh_token, expires_at
    if not refresh_token:
        raise ValueError("Not connected to TikTok — authorize in the API tab first.")
    out = refresh_access_token(client_key=client_key, client_secret=client_secret, refresh_token=refresh_token)
    p = parse_token_response(out)
    exp = now + float(p["expires_in"])
    return p["access_token"], p.get("refresh_token") or refresh_token, exp


def _json_post_authed(url: str, access_token: str, body: dict[str, Any], timeout_s: int = 120) -> dict[str, Any]:
    import json

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _put_video_chunk(upload_url: str, chunk: bytes, content_type: str, byte_start: int, byte_end: int, total: int) -> None:
    cr = f"bytes {byte_start}-{byte_end}/{total}"
    req = urllib.request.Request(
        upload_url,
        data=chunk,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(chunk)),
            "Content-Range": cr,
        },
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        if resp.status not in (200, 201):
            raise ValueError(f"Upload PUT failed: HTTP {resp.status}")


def upload_local_video_to_inbox(access_token: str, video_path: Path) -> tuple[str, str]:
    """
    Upload MP4 to creator inbox (video.upload scope). User finishes posting in TikTok app.
    Returns (publish_id, status_message).
    """
    video_path = video_path.resolve()
    if not video_path.is_file():
        raise FileNotFoundError(str(video_path))
    size = video_path.stat().st_size
    if size <= 0:
        raise ValueError("Video file is empty")
    chunk_size = size
    total_chunks = 1
    body = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks,
        }
    }
    resp = _json_post_authed(INBOX_INIT_URL, access_token, body)
    err = (resp.get("error") or {}) if isinstance(resp, dict) else {}
    if err.get("code") and str(err.get("code")).lower() != "ok":
        raise ValueError(str(err.get("message") or err.get("code") or resp))
    data = resp.get("data") or {}
    upload_url = str(data.get("upload_url") or "")
    publish_id = str(data.get("publish_id") or "")
    if not upload_url:
        raise ValueError(f"TikTok init missing upload_url: {resp}")
    raw_file = video_path.read_bytes()
    _put_video_chunk(upload_url, raw_file, "video/mp4", 0, size - 1, size)
    return publish_id, "Uploaded to TikTok inbox — open the TikTok app to finish posting."


def build_caption_package(video_dir: Path) -> tuple[str, str]:
    """(short_title, full caption for posting including hashtags)"""
    import json

    video_dir = video_dir.resolve()
    title = video_dir.name[:100]
    desc = ""
    meta = video_dir / "meta.json"
    if meta.exists():
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
            if isinstance(m, dict):
                if isinstance(m.get("title"), str) and m.get("title"):
                    title = str(m["title"])[:220]
                if isinstance(m.get("description"), str):
                    desc = str(m.get("description") or "").strip()[:2200]
        except Exception:
            pass
    tags = ""
    ht = video_dir / "hashtags.txt"
    if ht.exists():
        try:
            tags = " ".join(ht.read_text(encoding="utf-8").split())[:2000]
        except Exception:
            pass
    full = " ".join(x for x in (title, desc, tags) if x).strip()
    return title, full[:2200]
