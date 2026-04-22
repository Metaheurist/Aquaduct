from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from src.core.config import AppSettings
from src.platform.magichour_client import MagicHourRequestError, text_to_video_mp4_bytes
from src.platform.openai_client import build_image_generation_openai_client, build_openai_client_from_settings
from src.platform.replicate_client import ReplicateClient, ReplicateRequestError
from src.runtime.model_backend import effective_magic_hour_api_key, effective_replicate_api_token


def download_url_to_file(url: str, dest: Path, *, timeout: float = 180.0) -> None:
    r = requests.get(url.strip(), timeout=timeout)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)


def _image_provider(settings: AppSettings) -> tuple[str, str]:
    im = getattr(getattr(settings, "api_models", None), "image", None)
    return str(getattr(im, "provider", "") or "").strip().lower(), str(getattr(im, "model", "") or "").strip()


def generate_still_png_bytes(*, settings: AppSettings, prompt: str) -> bytes:
    prov, model = _image_provider(settings)
    if prov == "openai":
        client = build_openai_client_from_settings(settings)
        m = model or "dall-e-3"
        size = "1024x1792" if m.startswith("dall-e-3") else "1024x1024"
        return client.download_image_png(model=m, prompt=prompt, size=size)
    if prov == "siliconflow":
        client = build_image_generation_openai_client(settings)
        m = (model or "").strip() or "black-forest-labs/FLUX.1-schnell"
        return client.download_image_png(model=m, prompt=prompt, size="1024x1024")
    if prov == "replicate":
        tok = effective_replicate_api_token(settings)
        if not tok:
            raise ReplicateRequestError("Replicate token missing — set REPLICATE_API_TOKEN.")
        if not model:
            raise ReplicateRequestError("Replicate image model/version id is empty.")
        rc = ReplicateClient(api_token=tok)
        out = rc.run_prediction(version=model, input_payload={"prompt": prompt})
        urls: list[str] = []
        if isinstance(out, str):
            urls = [out]
        elif isinstance(out, list) and out:
            if isinstance(out[0], str):
                urls = [u for u in out if isinstance(u, str)]
            elif isinstance(out[0], dict) and "url" in out[0]:
                urls = [str(out[0]["url"])]
        if not urls:
            raise ReplicateRequestError("Replicate image output had no URL.")
        r = requests.get(urls[0], timeout=180)
        r.raise_for_status()
        return r.content
    raise RuntimeError(f"Unsupported image API provider: {prov!r}")


def cloud_video_mp4_paths(*, settings: AppSettings, prompts: list[str], out_dir: Path, pro_clip_seconds: float = 4.0) -> list[Path]:
    """Pro-mode cloud clips: Replicate (version id) or Magic Hour (model id, REST)."""
    vid = getattr(getattr(settings, "api_models", None), "video", None)
    prov = str(getattr(vid, "provider", "") or "").strip().lower()
    model = str(getattr(vid, "model", "") or "").strip()
    if prov == "replicate":
        return replicate_video_mp4_paths(settings=settings, prompts=prompts, out_dir=out_dir)
    if prov == "magic_hour":
        tok = effective_magic_hour_api_key(settings)
        if not tok:
            raise MagicHourRequestError("Magic Hour API key missing — set MAGIC_HOUR_API_KEY.")
        m = (model or "").strip() or "default"
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        T = max(1.0, min(30.0, float(pro_clip_seconds or 4.0)))
        for i, pr in enumerate(prompts):
            if not (pr or "").strip():
                continue
            raw = text_to_video_mp4_bytes(
                api_key=tok,
                prompt=pr.strip(),
                model=m,
                end_seconds=T,
            )
            p = out_dir / f"clip_{i+1:03d}.mp4"
            p.write_bytes(raw)
            paths.append(p)
        return paths
    raise RuntimeError(f"Unsupported cloud video API provider: {prov!r}")


def replicate_video_mp4_paths(*, settings: AppSettings, prompts: list[str], out_dir: Path) -> list[Path]:
    vid = getattr(getattr(settings, "api_models", None), "video", None)
    prov = str(getattr(vid, "provider", "") or "").strip().lower()
    version = str(getattr(vid, "model", "") or "").strip()
    if prov != "replicate" or not version:
        raise ReplicateRequestError("Replicate video requires provider=replicate and a model version id.")
    tok = effective_replicate_api_token(settings)
    if not tok:
        raise ReplicateRequestError("Replicate token missing.")
    rc = ReplicateClient(api_token=tok)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, pr in enumerate(prompts):
        if not (pr or "").strip():
            continue
        out = rc.run_prediction(version=version, input_payload={"prompt": pr.strip()})
        url: str | None = None
        if isinstance(out, str):
            url = out
        elif isinstance(out, list) and out and isinstance(out[0], str):
            url = out[0]
        if not url:
            raise ReplicateRequestError("Replicate video output missing URL.")
        p = out_dir / f"clip_{i+1:03d}.mp4"
        download_url_to_file(url, p)
        paths.append(p)
    return paths
