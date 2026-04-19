from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass

from src.models.model_manager import ModelOption


@dataclass(frozen=True)
class HardwareInfo:
    os: str
    cpu: str
    ram_gb: float | None
    gpu_name: str | None
    vram_gb: float | None


def _get_ram_gb_windows() -> float | None:
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)) == 0:
            return None
        return float(mem.ullTotalPhys) / (1024**3)
    except Exception:
        return None


def _parse_nvidia_smi() -> tuple[str | None, float | None]:
    """
    Returns (gpu_name, vram_gb) using nvidia-smi if available.
    """
    try:
        p = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if p.returncode != 0:
            return None, None
        line = (p.stdout or "").strip().splitlines()[0].strip()
        # Example: "NVIDIA GeForce RTX 4060 Ti, 8192"
        parts = [x.strip() for x in line.split(",")]
        if not parts:
            return None, None
        name = parts[0]
        mem_mb = None
        if len(parts) > 1:
            try:
                mem_mb = float(parts[1])
            except Exception:
                mem_mb = None
        vram_gb = (mem_mb / 1024.0) if mem_mb else None
        return name, vram_gb
    except Exception:
        return None, None


def _torch_cuda_info() -> tuple[str | None, float | None]:
    try:
        import torch

        if not torch.cuda.is_available():
            return None, None
        idx = torch.cuda.current_device()
        name = torch.cuda.get_device_name(idx)
        props = torch.cuda.get_device_properties(idx)
        vram_gb = float(props.total_memory) / (1024**3)
        return name, vram_gb
    except Exception:
        return None, None


def _get_ram_gb_psutil() -> float | None:
    try:
        import psutil

        return float(psutil.virtual_memory().total) / (1024**3)
    except Exception:
        return None


def get_hardware_info() -> HardwareInfo:
    os_name = f"{platform.system()} {platform.release()} ({platform.version()})"
    cpu = platform.processor() or platform.machine() or "Unknown CPU"
    ram_gb = _get_ram_gb_windows() if os.name == "nt" else None
    if ram_gb is None:
        ram_gb = _get_ram_gb_psutil()

    gpu_name, vram_gb = _parse_nvidia_smi()
    if gpu_name is None:
        tname, tvram = _torch_cuda_info()
        gpu_name = tname
        vram_gb = tvram

    return HardwareInfo(os=os_name, cpu=cpu, ram_gb=ram_gb, gpu_name=gpu_name, vram_gb=vram_gb)


def fit_marker_display(marker: str) -> str:
    """
    User-facing label for fit badges and tables.

    Internal codes (e.g. ``NO_GPU``) are unchanged for logic, tests, and ranking.
    """
    m = (marker or "").strip().upper()
    if m == "NO_GPU":
        return "VRAM Limit"
    return (marker or "").strip() or "UNKNOWN"


def rate_model_fit(*, kind: str, speed: str, vram_gb: float | None, ram_gb: float | None) -> tuple[str, str]:
    """
    Returns (marker, rationale) where marker is one of:
    - EXCELLENT / OK / RISKY / NO_GPU / UNKNOWN
    Simple heuristic rules for this project's workloads (conservative, not benchmarks).
    """
    if vram_gb is None:
        return "UNKNOWN", "GPU VRAM not detected (will fall back to CPU / placeholders where possible)."

    # Baseline requirements by kind
    if kind in ("image", "video"):
        # Image T2I / video diffusion: SDXL Turbo class ~6–8GB
        if vram_gb >= 10:
            return "EXCELLENT", "Plenty of VRAM for diffusion + overhead."
        if vram_gb >= 8:
            return "OK", "Should run FP16 image/video models; keep other models unloaded."
        if vram_gb >= 6:
            return "RISKY", "May run with tight headroom; expect occasional OOM depending on drivers."
        return "NO_GPU", "Likely too little VRAM; may use placeholder images or fail to load."

    if kind == "script":
        # 3B 4-bit is relatively light; speed label influences expectations slightly.
        need = 3.0 if speed in ("fastest", "faster") else 5.0
        if vram_gb >= max(8.0, need):
            return "EXCELLENT", "LLM 4-bit should fit comfortably."
        if vram_gb >= need:
            return "OK", "LLM 4-bit likely fits; keep batch small and unload between stages."
        return "RISKY", "LLM may fail on GPU; pipeline can fall back to template scripting."

    if kind == "voice":
        # Kokoro integration may run CPU; VRAM not critical for MVP.
        return "OK", "Voice can run via offline fallback; Kokoro download is optional."

    return "UNKNOWN", "Unknown model kind."


def vram_requirement_hint(
    *,
    kind: str,
    repo_id: str,
    speed: str,
    pair_image_repo_id: str = "",
) -> str:
    """
    Short UI label for typical GPU VRAM needs (heuristic, not a guarantee).
    Shown next to OK/RISKY badges in Settings.
    """
    rid = (repo_id or "").strip()
    spd = (speed or "slow").lower()
    pair = (pair_image_repo_id or "").strip()

    if kind == "voice":
        rl = rid.lower()
        if "xtts" in rl or "coqui" in rl:
            return "~ 4-6 GB VRAM"
        if "bark" in rl or "/bark" in rl:
            return "~ 8-12 GB VRAM"
        if "parler" in rl:
            return "~ 4-8 GB VRAM"
        return "CPU OK"

    if kind == "script":
        if spd == "fastest":
            return "~ 3 GB VRAM"
        if spd == "faster":
            return "~ 4 GB VRAM"
        return "~ 6-8 GB VRAM"

    if kind == "image":
        rl = rid.lower()
        if "stable-diffusion-xl-base" in rl and "turbo" not in rl:
            return "~ 8-10 GB VRAM"
        if "sdxl-turbo" in rl or rl.endswith("sdxl-turbo"):
            return "~ 6-8 GB VRAM"
        if "stable-diffusion-v1-5" in rl or "v1-5" in rl:
            return "~ 4-6 GB VRAM"
        return "~ 6-8 GB VRAM"

    if kind == "video":
        if pair:
            return "~ 10-12 GB VRAM"
        rl = rid.lower()
        if "stable-diffusion-xl-base" in rl and "turbo" not in rl:
            return "~ 8-10 GB VRAM"
        if "sdxl-turbo" in rl or rl.endswith("sdxl-turbo"):
            return "~ 6-8 GB VRAM"
        if "stable-diffusion-v1-5" in rl or "v1-5" in rl:
            return "~ 4-6 GB VRAM"
        if "zeroscope" in rl:
            return "~ 6-8 GB VRAM"
        if "stable-video-diffusion" in rl:
            return "~ 8-10 GB VRAM"
        return "~ 6-8 GB VRAM"

    return "--"


def rate_model_fit_for_repo(
    *,
    kind: str,
    speed: str,
    repo_id: str,
    pair_image_repo_id: str = "",
    vram_gb: float | None,
    ram_gb: float | None,
) -> tuple[str, str]:
    """
    Like `rate_model_fit`, but can take the actual repo_id (and optional paired image repo)
    to estimate fit more accurately for video/image models.
    """
    if vram_gb is None:
        return "UNKNOWN", "GPU VRAM not detected (will fall back to CPU / placeholders where possible)."

    k = (kind or "").strip().lower()
    rid = (repo_id or "").strip().lower()
    pair = (pair_image_repo_id or "").strip()

    if k == "image":
        if "stable-diffusion-v1-5" in rid or "v1-5" in rid:
            need_ok = 6.0
            need_ex = 8.0
            why = "SD 1.5 is relatively light."
        elif "stable-diffusion-xl-base" in rid and "turbo" not in rid:
            need_ok = 10.0
            need_ex = 14.0
            why = "SDXL Base is heavier than SDXL Turbo."
        else:
            need_ok = 8.0
            need_ex = 10.0
            why = "SDXL Turbo class expectation."
        if vram_gb >= need_ex:
            return "EXCELLENT", f"{why} VRAM looks comfortable."
        if vram_gb >= need_ok:
            return "OK", f"{why} Should run if models are unloaded between stages."
        if vram_gb >= max(4.0, need_ok - 2.0):
            return "RISKY", f"{why} Tight headroom; may OOM depending on drivers/settings."
        return "NO_GPU", f"{why} Likely too little VRAM; will use placeholders or fail to load."

    if k == "video":
        # Motion / latent video models (not T2I — see kind "image").
        if pair:
            need_ok = 12.0
            need_ex = 16.0
            why = "Paired pipeline (keyframes + img->vid) is heavier; unloading between stages helps."
        elif "stable-video-diffusion" in rid or "img2vid" in rid:
            need_ok = 10.0
            need_ex = 14.0
            why = "Image-to-video diffusion is VRAM-heavy."
        elif "zeroscope" in rid:
            need_ok = 6.0
            need_ex = 10.0
            why = "Text-to-video at 576w is moderate weight."
        else:
            need_ok = 8.0
            need_ex = 12.0
            why = "Video diffusion class expectation."

        if vram_gb >= need_ex:
            return "EXCELLENT", f"{why} VRAM looks comfortable."
        if vram_gb >= need_ok:
            return "OK", f"{why} Should run if models are unloaded between stages."
        if vram_gb >= max(4.0, need_ok - 2.0):
            return "RISKY", f"{why} Tight headroom; may OOM depending on drivers/settings."
        return "NO_GPU", f"{why} Likely too little VRAM; will use placeholders or fail to load."

    # For script/voice, keep the existing heuristic (speed-based).
    return rate_model_fit(kind=kind, speed=speed, vram_gb=vram_gb, ram_gb=ram_gb)


def marker_rank(marker: str) -> int:
    m = (marker or "").upper().strip()
    return {"EXCELLENT": 4, "OK": 3, "RISKY": 2, "UNKNOWN": 1, "NO_GPU": 0}.get(m, 0)


def voice_fit_marker(repo_id: str, vram_gb: float | None) -> tuple[str, str]:
    """
    Tighter fit labels for TTS repos than generic ``rate_model_fit`` (which treats most voice as OK).
    """
    rid = (repo_id or "").strip().lower()
    if not rid:
        return "UNKNOWN", "Empty repo id"
    if vram_gb is None:
        if any(x in rid for x in ("bark", "xtts", "coqui")):
            return "RISKY", "VRAM not detected; heavy TTS may be risky on this PC."
        if "parler" in rid:
            return "OK", "VRAM not detected; Parler may still work on CPU."
        return "EXCELLENT", "Lightweight TTS is usually fine on CPU."
    if "bark" in rid:
        if vram_gb >= 10:
            return "EXCELLENT", "Bark fits this VRAM budget."
        if vram_gb >= 8:
            return "OK", "Bark should run with some headroom."
        if vram_gb >= 6:
            return "RISKY", "Bark may be tight on this GPU."
        return "NO_GPU", "Likely too little VRAM for Bark."
    if "xtts" in rid or "coqui" in rid:
        if vram_gb >= 8:
            return "EXCELLENT", "XTTS fits comfortably."
        if vram_gb >= 5:
            return "OK", "XTTS should fit."
        if vram_gb >= 4:
            return "RISKY", "XTTS may be tight."
        return "NO_GPU", "Likely too little VRAM for XTTS."
    if "parler" in rid:
        if vram_gb >= 6:
            return "OK", "Parler-TTS is reasonable for this GPU."
        if vram_gb >= 4:
            return "RISKY", "Parler may be tight."
        return "NO_GPU", "Likely too little VRAM for Parler."
    if "speecht5" in rid:
        if vram_gb >= 4:
            return "OK", "SpeechT5 should run."
        return "RISKY", "Little VRAM; prefer Kokoro or MMS-TTS."
    return "EXCELLENT", "Lightweight TTS checkpoint."


_SCRIPT_SPEED_RANK = {"fastest": 0, "faster": 1, "slow": 2}

# Lower index = preferred when GPU fit is equal (SDXL Turbo default balance).
_IMAGE_PREF_ORDER: tuple[str, ...] = (
    "stabilityai/sdxl-turbo",
    "runwayml/stable-diffusion-v1-5",
    "stabilityai/stable-diffusion-xl-base-1.0",
)

_MOTION_VIDEO_PREF_ORDER: tuple[str, ...] = (
    "cerspense/zeroscope_v2_576w",
    "stabilityai/stable-video-diffusion-img2vid-xt",
)

_VOICE_PREF_ORDER: tuple[str, ...] = (
    "hexgrad/Kokoro-82M",
    "facebook/mms-tts-eng",
    "myshell-ai/MeloTTS-English",
    "microsoft/speecht5_tts",
    "parler-tts/parler-tts-mini-v1",
    "coqui/XTTS-v2",
    "suno/bark",
)


def _image_pref_index(repo_id: str) -> int:
    try:
        return _IMAGE_PREF_ORDER.index(repo_id)
    except ValueError:
        return 50


def _motion_video_pref_index(repo_id: str) -> int:
    try:
        return _MOTION_VIDEO_PREF_ORDER.index(repo_id)
    except ValueError:
        return 50


def _voice_pref_index(repo_id: str) -> int:
    try:
        return _VOICE_PREF_ORDER.index(repo_id)
    except ValueError:
        return 50


@dataclass(frozen=True)
class AutoFitRanked:
    """Best-first repo choices for Settings -> Model -> Auto-fit (see ``rank_models_for_auto_fit``)."""

    script_repo_ids: tuple[str, ...]
    image_repo_ids: tuple[str, ...]
    video_repo_ids: tuple[str, ...]
    voice_repo_ids: tuple[str, ...]
    log_summary: str


def rank_models_for_auto_fit(model_options: list[ModelOption], hw: HardwareInfo) -> AutoFitRanked:
    """
    Order curated models by fit for this machine: script (LLM), image (T2I), video (motion), voice (TTS).
    First entries are the strongest matches; the UI applies the first **enabled** row per combo.
    """
    vram = hw.vram_gb
    ram = hw.ram_gb

    script_opts = [o for o in model_options if o.kind == "script"]
    image_opts = [o for o in model_options if o.kind == "image"]
    video_opts = [o for o in model_options if o.kind == "video"]
    voice_opts = [o for o in model_options if o.kind == "voice"]

    def script_key(o: ModelOption) -> tuple[float, float]:
        m, _ = rate_model_fit_for_repo(
            kind="script",
            speed=o.speed,
            repo_id=o.repo_id,
            vram_gb=vram,
            ram_gb=ram,
        )
        rk = float(marker_rank(m))
        spd = float(_SCRIPT_SPEED_RANK.get(o.speed, 0))
        return (-rk, -spd)

    def image_key(o: ModelOption) -> tuple[float, float]:
        m, _ = rate_model_fit_for_repo(
            kind="image",
            speed=o.speed,
            repo_id=o.repo_id,
            vram_gb=vram,
            ram_gb=ram,
        )
        rk = float(marker_rank(m))
        pref = float(_image_pref_index(o.repo_id))
        return (-rk, pref)

    def video_key(o: ModelOption) -> tuple[float, float]:
        pair = str(getattr(o, "pair_image_repo_id", "") or "").strip()
        m, _ = rate_model_fit_for_repo(
            kind="video",
            speed=o.speed,
            repo_id=o.repo_id,
            pair_image_repo_id=pair,
            vram_gb=vram,
            ram_gb=ram,
        )
        rk = float(marker_rank(m))
        pref = float(_motion_video_pref_index(o.repo_id))
        return (-rk, pref)

    def voice_key(o: ModelOption) -> tuple[float, float]:
        m, _ = voice_fit_marker(o.repo_id, vram)
        rk = float(marker_rank(m))
        pref = float(_voice_pref_index(o.repo_id))
        return (-rk, pref)

    script_sorted = sorted(script_opts, key=script_key)
    image_sorted = sorted(image_opts, key=image_key)
    # Prefer SDXL Turbo over SD 1.5 at ~8GB when both are OK (project default balance).
    if vram is not None and vram >= 8.0:
        turbo_o = next((o for o in image_opts if o.repo_id == "stabilityai/sdxl-turbo"), None)
        if turbo_o is not None:
            m_t, _ = rate_model_fit_for_repo(
                kind="image",
                speed=turbo_o.speed,
                repo_id=turbo_o.repo_id,
                vram_gb=vram,
                ram_gb=ram,
            )
            if marker_rank(m_t) >= marker_rank("OK") and image_sorted:
                first = image_sorted[0]
                if first.repo_id == "runwayml/stable-diffusion-v1-5":
                    rest = [o for o in image_sorted if o.repo_id != "stabilityai/sdxl-turbo"]
                    image_sorted = [turbo_o] + rest
    video_sorted = sorted(video_opts, key=video_key)
    voice_sorted = sorted(voice_opts, key=voice_key)

    script_ids = tuple(o.repo_id for o in script_sorted)
    image_ids = tuple(o.repo_id for o in image_sorted)
    video_ids = tuple(o.repo_id for o in video_sorted)
    voice_ids = tuple(o.repo_id for o in voice_sorted)

    by_repo = {o.repo_id: o for o in model_options}
    gpu_lbl = hw.gpu_name or "GPU unknown"
    v_lbl = f"{hw.vram_gb:.1f} GB" if hw.vram_gb is not None else "VRAM n/a"
    r_lbl = f"{hw.ram_gb:.1f} GB RAM" if hw.ram_gb is not None else "RAM n/a"

    def _label(rid: str) -> str:
        o = by_repo.get(rid)
        return o.label if o else rid

    pick_s = script_sorted[0].repo_id if script_sorted else ""
    pick_i = image_sorted[0].repo_id if image_sorted else ""
    pick_v = video_sorted[0].repo_id if video_sorted else ""
    pick_c = voice_sorted[0].repo_id if voice_sorted else ""

    log_summary = (
        f"Auto-fit ({gpu_lbl}, {v_lbl}, {r_lbl}) -> "
        f"Script: {_label(pick_s)} | Image: {_label(pick_i)} | Video: {_label(pick_v)} | Voice: {_label(pick_c)}"
    )

    return AutoFitRanked(
        script_repo_ids=script_ids,
        image_repo_ids=image_ids,
        video_repo_ids=video_ids,
        voice_repo_ids=voice_ids,
        log_summary=log_summary,
    )

