from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass


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


def get_hardware_info() -> HardwareInfo:
    os_name = f"{platform.system()} {platform.release()} ({platform.version()})"
    cpu = platform.processor() or platform.machine() or "Unknown CPU"
    ram_gb = _get_ram_gb_windows() if os.name == "nt" else None

    gpu_name, vram_gb = _parse_nvidia_smi()
    if gpu_name is None:
        tname, tvram = _torch_cuda_info()
        gpu_name = tname
        vram_gb = tvram

    return HardwareInfo(os=os_name, cpu=cpu, ram_gb=ram_gb, gpu_name=gpu_name, vram_gb=vram_gb)


def rate_model_fit(*, kind: str, speed: str, vram_gb: float | None, ram_gb: float | None) -> tuple[str, str]:
    """
    Returns (marker, rationale) where marker is one of:
    - EXCELLENT / OK / RISKY / NO_GPU / UNKNOWN
    Simple heuristic rules for this project’s workloads (conservative, not benchmarks).
    """
    if vram_gb is None:
        return "UNKNOWN", "GPU VRAM not detected (will fall back to CPU / placeholders where possible)."

    # Baseline requirements by kind
    if kind == "video":
        # SDXL Turbo tends to want ~6-8GB VRAM
        if vram_gb >= 10:
            return "EXCELLENT", "Plenty of VRAM for SDXL Turbo + overhead."
        if vram_gb >= 8:
            return "OK", "Should run SDXL Turbo FP16; keep other models unloaded."
        if vram_gb >= 6:
            return "RISKY", "May run with tight headroom; expect occasional OOM depending on drivers."
        return "NO_GPU", "Likely too little VRAM for SDXL Turbo; will use placeholder images."

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
        if "xtts" in rid.lower() or "coqui" in rid.lower():
            return "≈ 4–6 GB VRAM"
        return "CPU OK"

    if kind == "script":
        if spd == "fastest":
            return "≈ 3 GB VRAM"
        if spd == "faster":
            return "≈ 4 GB VRAM"
        return "≈ 6–8 GB VRAM"

    if kind == "video":
        if pair:
            return "≈ 10–12 GB VRAM"
        rl = rid.lower()
        if "stable-diffusion-xl-base" in rl and "turbo" not in rl:
            return "≈ 8–10 GB VRAM"
        if "sdxl-turbo" in rl or rl.endswith("sdxl-turbo"):
            return "≈ 6–8 GB VRAM"
        if "stable-diffusion-v1-5" in rl or "v1-5" in rl:
            return "≈ 4–6 GB VRAM"
        if "zeroscope" in rl:
            return "≈ 6–8 GB VRAM"
        if "stable-video-diffusion" in rl:
            return "≈ 8–10 GB VRAM"
        return "≈ 6–8 GB VRAM"

    return "—"

