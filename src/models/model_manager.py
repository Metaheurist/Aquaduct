from __future__ import annotations

import os
import re
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ModelOption:
    label: str
    repo_id: str
    speed: str  # "fastest" | "faster" | "slow"
    kind: str  # "script" | "video" | "voice"
    order: int = 0  # UI enumeration within kind
    pair_image_repo_id: str = ""  # for img->vid options, which image model to use for keyframes
    size_hint: str = ""  # e.g. "82M", "3B", or "~6-8GB"


def model_options() -> list[ModelOption]:
    """
    Curated options for the UI. These are defaults; users can still override by typing IDs.
    Speed is relative: fastest < faster < slow (quality tends to increase with slower models).
    """
    opts = [
        # Script (LLM)
        ModelOption("Qwen2.5 1.5B Instruct (very small)", "Qwen/Qwen2.5-1.5B-Instruct", "fastest", "script", size_hint="1.5B"),
        ModelOption("Qwen2.5 3B Instruct", "Qwen/Qwen2.5-3B-Instruct", "faster", "script", size_hint="3B"),
        ModelOption("Phi-3.5 Mini Instruct (small but strong)", "microsoft/Phi-3.5-mini-instruct", "faster", "script", size_hint="mini"),
        ModelOption("Llama 3.2 3B Instruct (4-bit target)", "meta-llama/Llama-3.2-3B-Instruct", "faster", "script", size_hint="3B"),
        ModelOption("Mistral 7B Instruct v0.3 (heavier)", "mistralai/Mistral-7B-Instruct-v0.3", "slow", "script", size_hint="7B"),
        ModelOption("Qwen2.5 7B Instruct (heavier)", "Qwen/Qwen2.5-7B-Instruct", "slow", "script", size_hint="7B"),
        ModelOption("Llama 3.1 8B Instruct (heavier)", "meta-llama/Meta-Llama-3.1-8B-Instruct", "slow", "script", size_hint="8B"),
        # Video/Images (diffusion)
        ModelOption("SDXL Turbo (1-step images)", "stabilityai/sdxl-turbo", "fastest", "video", size_hint="~6-8GB"),
        ModelOption("SD 1.5 (images, lightweight)", "runwayml/stable-diffusion-v1-5", "faster", "video", size_hint="~4-6GB"),
        ModelOption("SDXL Base 1.0 (images, higher quality)", "stabilityai/stable-diffusion-xl-base-1.0", "slow", "video", size_hint="~8-10GB"),
        # Paired pipelines (single selection): keyframes via SDXL Turbo, then animate with img->vid
        ModelOption(
            "SVD XT (img->vid clips) + SDXL Turbo keyframes",
            "stabilityai/stable-video-diffusion-img2vid-xt",
            "slow",
            "video",
            pair_image_repo_id="stabilityai/sdxl-turbo",
            size_hint="~10-12GB",
        ),
        ModelOption("ZeroScope v2 576w (clips, text->vid)", "cerspense/zeroscope_v2_576w", "slow", "video", size_hint="~6-8GB"),
        # Voice (TTS) - Hugging Face snapshots for local weights (pipeline TTS path is still ElevenLabs -> Kokoro hook -> pyttsx3)
        ModelOption("Kokoro 82M", "hexgrad/Kokoro-82M", "fastest", "voice", size_hint="82M"),
        ModelOption("MMS-TTS English (Meta, lightweight)", "facebook/mms-tts-eng", "faster", "voice", size_hint="MMS-TTS"),
        ModelOption("MeloTTS English", "myshell-ai/MeloTTS-English", "faster", "voice", size_hint="MeloTTS"),
        ModelOption("SpeechT5 TTS (Microsoft)", "microsoft/speecht5_tts", "faster", "voice", size_hint="SpeechT5"),
        ModelOption("Parler-TTS mini v1 (expressive)", "parler-tts/parler-tts-mini-v1", "slow", "voice", size_hint="Parler mini"),
        ModelOption("coqui XTTS v2 (higher quality, heavier)", "coqui/XTTS-v2", "slow", "voice", size_hint="XTTS v2"),
        ModelOption("Bark (high quality, very large)", "suno/bark", "slow", "voice", size_hint="Bark"),
    ]

    speed_rank = {"fastest": 0, "faster": 1, "slow": 2}
    kind_rank = {"script": 0, "video": 1, "voice": 2}
    opts.sort(key=lambda o: (kind_rank.get(o.kind, 99), speed_rank.get(o.speed, 99), o.label.lower()))

    # Enumerate within each kind (easiest-to-run first)
    counters: dict[str, int] = {}
    out: list[ModelOption] = []
    for o in opts:
        counters[o.kind] = counters.get(o.kind, 0) + 1
        out.append(
            ModelOption(
                o.label,
                o.repo_id,
                o.speed,
                o.kind,
                counters[o.kind],
                o.pair_image_repo_id,
                o.size_hint,
            )
        )
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


def project_dirname_to_repo_id(dirname: str) -> str | None:
    """
    Reverse of ``project_model_dirname``: ``owner__repo-name`` -> ``owner/repo-name``.
    Uses the first ``__`` only (matches how we encode ``/``).
    """
    d = str(dirname or "").strip()
    if "__" not in d:
        return None
    a, b = d.split("__", 1)
    a, b = a.strip(), b.strip()
    if not a or not b:
        return None
    return f"{a}/{b}"


def find_repo_dirs_in_folder(folder: Path, repo_ids: set[str]) -> list[tuple[str, Path]]:
    """Discover curated model repo directories under a selected folder.

    This supports selecting either a parent folder containing safe-encoded model dirs,
    a folder that contains a nested ``models/`` tree with owner/repo children, or a
    direct ``owner/repo`` tree under the selected folder.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return []

    out: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def _add(repo_id: str, path: Path) -> None:
        rid = str(repo_id or "").strip()
        if not rid or rid in seen or rid not in repo_ids:
            return
        seen.add(rid)
        out.append((rid, path))

    maybe_self = project_dirname_to_repo_id(folder.name)
    if maybe_self:
        _add(maybe_self, folder)

    def _inspect_parent(parent: Path, owner_name: str | None = None) -> None:
        for child in sorted(parent.iterdir()):
            if not child.is_dir():
                continue

            maybe_repo = project_dirname_to_repo_id(child.name)
            if maybe_repo:
                _add(maybe_repo, child)
                continue

            if owner_name:
                candidate = f"{owner_name}/{child.name}"
                _add(candidate, child)
                continue

            if child.name.lower() == "models":
                _inspect_parent(child)
                continue

            for subchild in sorted(child.iterdir()):
                if not subchild.is_dir():
                    continue
                candidate = f"{child.name}/{subchild.name}"
                _add(candidate, subchild)

    _inspect_parent(folder)
    return out


@dataclass(frozen=True)
class ModelIntegrityReport:
    """Result of comparing a local ``models/<encoded-repo>/`` tree to the Hugging Face Hub."""

    repo_id: str
    ok: bool
    revision: str = ""
    checked_files: int = 0
    missing_paths: list[str] = field(default_factory=list)
    extra_paths: list[str] = field(default_factory=list)
    mismatches: list[dict[str, str]] = field(default_factory=list)
    error: str = ""
    warning: str = ""


def verify_project_model_integrity(
    repo_id: str,
    *,
    models_dir: Path,
    token: str | bool | None = None,
) -> ModelIntegrityReport:
    """
    Verify a project-local snapshot using Hugging Face Hub metadata.

    Uses ``huggingface_hub.HfApi.verify_repo_checksums``: LFS files are checked with SHA-256,
    non-LFS files with the git blob id (SHA-1). Requires network access.

    A report with ``ok=False`` means missing files, hash mismatches (corruption), or an error
    (e.g. offline, wrong token for a gated repo).
    """
    rid = str(repo_id or "").strip()
    if not rid:
        return ModelIntegrityReport(repo_id=repo_id, ok=False, error="empty repo id")

    local_dir = models_dir / project_model_dirname(rid)
    if not local_dir.is_dir():
        return ModelIntegrityReport(repo_id=rid, ok=False, error="not installed under models/")

    if _dir_size_bytes(local_dir) < int(min_bytes_for_snapshot()):
        return ModelIntegrityReport(repo_id=rid, ok=False, error="folder too small; looks incomplete or empty")

    try:
        from huggingface_hub import HfApi  # type: ignore

        tok = _hf_token() if token is None else token
        api = HfApi(token=tok)
        fv = api.verify_repo_checksums(rid, local_dir=str(local_dir.resolve()))
    except Exception as e:
        msg = str(e).strip() or type(e).__name__
        if len(msg) > 500:
            msg = msg[:497] + "..."
        return ModelIntegrityReport(repo_id=rid, ok=False, error=msg)

    mismatches: list[dict[str, str]] = []
    for m in fv.mismatches:
        if isinstance(m, dict):
            mismatches.append(
                {
                    "path": str(m.get("path", "")),
                    "expected": str(m.get("expected", "")),
                    "actual": str(m.get("actual", "")),
                    "algorithm": str(m.get("algorithm", "")),
                }
            )

    missing = list(fv.missing_paths)
    extra = list(fv.extra_paths)
    failed = len(missing) > 0 or len(mismatches) > 0
    warn = ""
    if extra:
        n = len(extra)
        preview = ", ".join(extra[:5])
        if n > 5:
            preview += f", ... (+{n - 5} more)"
        warn = f"{n} unexpected extra file(s) on disk (not on Hub main tree): {preview}"

    return ModelIntegrityReport(
        repo_id=rid,
        ok=not failed,
        revision=str(fv.revision or ""),
        checked_files=int(fv.checked_count),
        missing_paths=missing,
        extra_paths=extra,
        mismatches=mismatches,
        error="",
        warning=warn,
    )


def min_bytes_for_snapshot() -> int:
    """Minimum on-disk bytes to treat a folder as a plausible model snapshot (see ``model_has_local_snapshot``)."""
    return 256_000


def list_installed_repo_ids_from_disk(models_dir: Path) -> list[str]:
    """
    Discover ``repo_id`` values that have a non-trivial folder under ``models_dir/``.
    """
    models_dir = Path(models_dir)
    if not models_dir.is_dir():
        return []
    out: list[str] = []
    seen: set[str] = set()
    try:
        for p in sorted(models_dir.iterdir()):
            if not p.is_dir():
                continue

            # Safe-encoded folder names, e.g. owner__repo-name
            rid = project_dirname_to_repo_id(p.name)
            if rid and model_has_local_snapshot(rid, models_dir=models_dir, min_bytes=min_bytes_for_snapshot()):
                if rid not in seen:
                    seen.add(rid)
                    out.append(rid)
                continue

            # Nested owner/repo layout: models_dir/owner/repo
            for child in sorted(p.iterdir()):
                if not child.is_dir():
                    continue
                candidate = f"{p.name}/{child.name}"
                if model_has_local_snapshot(candidate, models_dir=models_dir, min_bytes=min_bytes_for_snapshot()):
                    if candidate not in seen:
                        seen.add(candidate)
                        out.append(candidate)
    except Exception:
        return out
    return out


def _iter_files(root: Path) -> Iterable[Path]:
    try:
        for p in root.rglob("*"):
            yield p
    except Exception:
        return


def _dir_size_bytes(root: Path) -> int:
    """
    Best-effort recursive directory size in bytes.
    Avoids following symlinks (Windows-safe) and ignores stat errors.
    """
    total = 0
    for p in _iter_files(root):
        try:
            if p.is_symlink():
                continue
            if p.is_file():
                total += int(p.stat().st_size)
        except Exception:
            continue
    return int(total)


def _human_bytes(n: int | float | None) -> str:
    if n is None:
        return "--"
    try:
        x = float(n)
    except Exception:
        return "--"
    if x <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    u = 0
    while x >= 1024.0 and u < len(units) - 1:
        x /= 1024.0
        u += 1
    if u == 0:
        return f"{int(x)} {units[u]}"
    return f"{x:.1f} {units[u]}"


def _find_local_snapshot_dir(repo_id: str, models_dir: Path) -> Path | None:
    """Return the local project snapshot directory for a repo_id, if it exists."""
    rid = str(repo_id or "").strip()
    if not rid:
        return None

    candidate = models_dir / project_model_dirname(rid)
    if candidate.is_dir():
        return candidate

    nested = models_dir / rid
    if nested.is_dir():
        return nested

    underscore = models_dir / rid.replace("/", "_")
    if underscore.is_dir():
        return underscore

    return None


def local_model_size_label(repo_id: str, *, models_dir: Path) -> str:
    """
    Returns a human-readable local size for a repo_id in the project `models/` folder.
    If not downloaded, returns "--".
    """
    p = _find_local_snapshot_dir(repo_id, models_dir)
    if p is None:
        return "--"
    return _human_bytes(_dir_size_bytes(p))


def model_size_label(repo_id: str, *, models_dir: Path, size_hint: str = "") -> str:
    """
    Prefer actual local on-disk size (if downloaded), else fall back to size_hint, else "--".
    """
    local = local_model_size_label(repo_id, models_dir=models_dir)
    if local != "--":
        return local
    hint = str(size_hint or "").strip()
    return hint or "--"


def hf_token() -> str | None:
    """Public accessor for the Hugging Face token (if configured)."""
    t = _hf_token()
    return str(t) if isinstance(t, str) and t.strip() else None


def remote_repo_size_bytes(repo_id: str, *, token: str | None = None, timeout_s: float = 20.0) -> int | None:
    """
    Best-effort total repo size (bytes) from Hugging Face Hub.
    Requires network; uses token if provided (recommended for gated repos / rate limits).
    """
    rid = str(repo_id or "").strip()
    if not rid:
        return None
    try:
        from huggingface_hub import HfApi  # type: ignore
    except Exception:
        return None

    try:
        api = HfApi(token=token or hf_token())
        # files_metadata=True includes per-file sizes when available
        info = api.model_info(repo_id=rid, files_metadata=True, timeout=timeout_s)
        sibs = getattr(info, "siblings", None) or []
        total = 0
        any_size = False
        for s in sibs:
            try:
                sz = getattr(s, "size", None)
                if sz is None:
                    continue
                total += int(sz)
                any_size = True
            except Exception:
                continue
        return int(total) if any_size else None
    except Exception:
        return None


def resolve_pretrained_load_path(repo_id: str, *, models_dir: Path) -> str:
    """
    Path passed to ``transformers`` / ``diffusers`` ``from_pretrained``.

    If the repo was saved under ``models_dir/<safe_repo>/`` (same layout as
    ``download_model_to_project``), returns that **absolute** directory so weights load
    from disk. Otherwise returns ``repo_id`` and Hugging Face will use the hub cache
    (may download into the cache even when Settings shows a project snapshot path).
    """
    rid = str(repo_id or "").strip()
    if not rid:
        return repo_id
    p = _find_local_snapshot_dir(rid, models_dir)
    if p is not None:
        return str(p.resolve())
    return rid


def model_has_local_snapshot(repo_id: str, *, models_dir: Path, min_bytes: int | None = None) -> bool:
    """
    True if a local project snapshot already exists and has at least ``min_bytes`` on disk.
    """
    p = _find_local_snapshot_dir(repo_id, models_dir)
    if p is None or not p.is_dir():
        return False
    mb = int(min_bytes) if min_bytes is not None else min_bytes_for_snapshot()
    return _dir_size_bytes(p) >= mb


def probe_hf_model(
    repo_id: str,
    *,
    token: str | None = None,
    timeout_s: float = 28.0,
) -> tuple[bool, int | None, str]:
    """
    Hit the Hugging Face Hub for ``repo_id`` metadata and summed file sizes.

    Returns ``(ok, total_bytes, error_message)``. ``ok`` is True when the repository
    is reachable and listing succeeds. ``error_message`` is empty on success.
    """
    rid = str(repo_id or "").strip()
    if not rid:
        return False, None, "empty repo id"
    try:
        from huggingface_hub import HfApi  # type: ignore
    except Exception:
        return False, None, "huggingface_hub is not available"

    try:
        api = HfApi(token=token or hf_token())
        info = api.model_info(repo_id=rid, files_metadata=True, timeout=timeout_s)
        sibs = getattr(info, "siblings", None) or []
        total = 0
        any_size = False
        for s in sibs:
            try:
                sz = getattr(s, "size", None)
                if sz is None:
                    continue
                total += int(sz)
                any_size = True
            except Exception:
                continue
        return True, (int(total) if any_size else None), ""
    except Exception as e:
        msg = str(e).strip() or type(e).__name__
        if len(msg) > 240:
            msg = msg[:237] + "..."
        return False, None, msg


def load_hf_size_cache(cache_path: Path) -> dict[str, int]:
    """
    Loads a simple {repo_id: bytes} cache file.
    """
    try:
        if not cache_path.exists():
            return {}
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        out: dict[str, int] = {}
        for k, v in data.items():
            if not isinstance(k, str):
                continue
            try:
                out[k] = int(v)
            except Exception:
                continue
        return out
    except Exception:
        return {}


def save_hf_size_cache(cache_path: Path, sizes: dict[str, int]) -> None:
    """
    Saves {repo_id: bytes} to disk (best-effort).
    """
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {str(k): int(v) for k, v in (sizes or {}).items() if str(k).strip()}
        cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


def best_model_size_label(
    repo_id: str,
    *,
    models_dir: Path,
    remote_sizes: dict[str, int] | None = None,
    size_hint: str = "",
) -> str:
    """
    Prefer local on-disk size, else remote HF size (if available), else size_hint.
    """
    local = local_model_size_label(repo_id, models_dir=models_dir)
    if local != "--":
        return local
    if remote_sizes:
        try:
            b = remote_sizes.get(str(repo_id).strip())
            if b is not None:
                return _human_bytes(int(b))
        except Exception:
            pass
    hint = str(size_hint or "").strip()
    return hint or "--"


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

    from debug import dprint

    models_dir.mkdir(parents=True, exist_ok=True)
    local_dir = models_dir / _safe_repo_dirname(repo_id)
    local_dir.mkdir(parents=True, exist_ok=True)
    dprint("models", "snapshot_download", f"repo={repo_id!r}", f"dest={local_dir.name}")

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

