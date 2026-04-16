from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelOption:
    label: str
    repo_id: str
    speed: str  # "fastest" | "faster" | "slow"
    kind: str  # "script" | "video" | "voice"
    order: int = 0  # UI enumeration within kind
    pair_image_repo_id: str = ""  # for img→vid options, which image model to use for keyframes


def model_options() -> list[ModelOption]:
    """
    Curated options for the UI. These are defaults; users can still override by typing IDs.
    Speed is relative: fastest < faster < slow (quality tends to increase with slower models).
    """
    opts = [
        # Script (LLM)
        ModelOption("Qwen2.5 1.5B Instruct (very small)", "Qwen/Qwen2.5-1.5B-Instruct", "fastest", "script"),
        ModelOption("Qwen2.5 3B Instruct", "Qwen/Qwen2.5-3B-Instruct", "faster", "script"),
        ModelOption("Phi-3.5 Mini Instruct (small but strong)", "microsoft/Phi-3.5-mini-instruct", "faster", "script"),
        ModelOption("Llama 3.2 3B Instruct (4-bit target)", "meta-llama/Llama-3.2-3B-Instruct", "faster", "script"),
        ModelOption("Mistral 7B Instruct v0.3 (heavier)", "mistralai/Mistral-7B-Instruct-v0.3", "slow", "script"),
        ModelOption("Qwen2.5 7B Instruct (heavier)", "Qwen/Qwen2.5-7B-Instruct", "slow", "script"),
        ModelOption("Llama 3.1 8B Instruct (heavier)", "meta-llama/Meta-Llama-3.1-8B-Instruct", "slow", "script"),
        # Video/Images (diffusion)
        ModelOption("SDXL Turbo (1-step images)", "stabilityai/sdxl-turbo", "fastest", "video"),
        ModelOption("SD 1.5 (images, lightweight)", "runwayml/stable-diffusion-v1-5", "faster", "video"),
        ModelOption("SDXL Base 1.0 (images, higher quality)", "stabilityai/stable-diffusion-xl-base-1.0", "slow", "video"),
        # Paired pipelines (single selection): keyframes via SDXL Turbo, then animate with img→vid
        ModelOption(
            "SVD XT (img→vid clips) + SDXL Turbo keyframes",
            "stabilityai/stable-video-diffusion-img2vid-xt",
            "slow",
            "video",
            pair_image_repo_id="stabilityai/sdxl-turbo",
        ),
        ModelOption("ZeroScope v2 576w (clips, text→vid)", "cerspense/zeroscope_v2_576w", "slow", "video"),
        # Voice (TTS)
        ModelOption("Kokoro 82M", "hexgrad/Kokoro-82M", "fastest", "voice"),
        ModelOption("coqui XTTS v2 (higher quality, heavier)", "coqui/XTTS-v2", "slow", "voice"),
    ]

    speed_rank = {"fastest": 0, "faster": 1, "slow": 2}
    kind_rank = {"script": 0, "video": 1, "voice": 2}
    opts.sort(key=lambda o: (kind_rank.get(o.kind, 99), speed_rank.get(o.speed, 99), o.label.lower()))

    # Enumerate within each kind (easiest-to-run first)
    counters: dict[str, int] = {}
    out: list[ModelOption] = []
    for o in opts:
        counters[o.kind] = counters.get(o.kind, 0) + 1
        out.append(ModelOption(o.label, o.repo_id, o.speed, o.kind, counters[o.kind], o.pair_image_repo_id))
    return out


def download_model(repo_id: str, *, cache_dir: Path) -> Path:
    """
    Downloads a model snapshot into the Hugging Face cache (or provided cache dir) and returns local path.
    """
    from huggingface_hub import snapshot_download

    cache_dir.mkdir(parents=True, exist_ok=True)
    local_dir = snapshot_download(
        repo_id=repo_id,
        cache_dir=str(cache_dir),
        local_dir=None,
    )
    return Path(local_dir)


def _safe_repo_dirname(repo_id: str) -> str:
    # e.g. "meta-llama/Llama-3.2-3B-Instruct" -> "meta-llama__Llama-3.2-3B-Instruct"
    s = repo_id.strip().replace("/", "__")
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    return s[:120] or "model"


def project_model_dirname(repo_id: str) -> str:
    """Folder name under `models/` for a Hugging Face repo id (matches `download_model_to_project`)."""
    return _safe_repo_dirname(repo_id)


def _hf_token() -> str | bool | None:
    """Prefer explicit token from env (HF_TOKEN / HUGGINGFACEHUB_API_TOKEN); else let hub use defaults."""
    for key in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN"):
        t = os.environ.get(key)
        if t and str(t).strip():
            return str(t).strip()
    return None  # huggingface_hub falls back to cached login / env


def download_model_to_project(repo_id: str, *, models_dir: Path, tqdm_class=None) -> Path:
    """
    Downloads a model snapshot into a project-local folder (no HF cache required).
    Returns the local directory path under `models_dir/`.
    """
    from huggingface_hub import snapshot_download

    models_dir.mkdir(parents=True, exist_ok=True)
    local_dir = models_dir / _safe_repo_dirname(repo_id)
    local_dir.mkdir(parents=True, exist_ok=True)

    token = _hf_token()
    max_workers = int(os.environ.get("HF_SNAPSHOT_MAX_WORKERS", "8"))
    max_workers = max(1, min(32, max_workers))

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        tqdm_class=tqdm_class,
        token=token,
        max_workers=max_workers,
        etag_timeout=float(os.environ.get("HF_ETAG_TIMEOUT", "30")),
    )
    return local_dir

