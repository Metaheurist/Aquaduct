from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class ModelOption:
    label: str
    repo_id: str
    speed: str  # "fastest" | "faster" | "slow"
    kind: str  # "script" | "video" | "voice"


def model_options() -> list[ModelOption]:
    """
    Curated options for the UI. These are defaults; users can still override by typing IDs.
    Speed is relative: fastest < faster < slow (quality tends to increase with slower models).
    """
    return [
        # Script (LLM)
        ModelOption("Llama 3.2 3B Instruct (4-bit target)", "meta-llama/Llama-3.2-3B-Instruct", "faster", "script"),
        ModelOption("Qwen2.5 1.5B Instruct (very small)", "Qwen/Qwen2.5-1.5B-Instruct", "fastest", "script"),
        ModelOption("Qwen2.5 3B Instruct", "Qwen/Qwen2.5-3B-Instruct", "faster", "script"),
        # Video/Images (diffusion)
        ModelOption("SDXL Turbo (1-step)", "stabilityai/sdxl-turbo", "fastest", "video"),
        # Voice (TTS)
        ModelOption("Kokoro 82M", "hexgrad/Kokoro-82M", "fastest", "voice"),
    ]


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
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    return Path(local_dir)


def _safe_repo_dirname(repo_id: str) -> str:
    # e.g. "meta-llama/Llama-3.2-3B-Instruct" -> "meta-llama__Llama-3.2-3B-Instruct"
    s = repo_id.strip().replace("/", "__")
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    return s[:120] or "model"


def download_model_to_project(repo_id: str, *, models_dir: Path) -> Path:
    """
    Downloads a model snapshot into a project-local folder (no HF cache required).
    Returns the local directory path under `models_dir/`.
    """
    from huggingface_hub import snapshot_download

    models_dir.mkdir(parents=True, exist_ok=True)
    local_dir = models_dir / _safe_repo_dirname(repo_id)
    local_dir.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    return local_dir

