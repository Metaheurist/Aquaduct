from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import Any

from src.models.model_manager import ModelOption
from src.util.cuda_capabilities import cuda_device_reported_by_torch


@dataclass(frozen=True)
class GpuDevice:
    """One CUDA device as detected by PyTorch (preferred) or nvidia-smi (fallback)."""

    index: int
    name: str
    total_vram_bytes: int
    multiprocessor_count: int = 0
    major: int = 0
    minor: int = 0
    clock_rate_khz: int = 0

    @property
    def total_vram_gb(self) -> float:
        return float(self.total_vram_bytes) / (1024**3)


@dataclass(frozen=True)
class HardwareInfo:
    os: str
    cpu: str
    ram_gb: float | None
    gpu_name: str | None
    vram_gb: float | None
    #: When multiple GPUs exist, comma-separated names (same order as ``list_cuda_gpus``).
    gpu_names_all: str | None = None


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
    Returns (gpu_name, vram_gb) using nvidia-smi if available (first GPU only).
    """
    gpus = _parse_nvidia_smi_all()
    if not gpus:
        return None, None
    g0 = gpus[0]
    return g0.name, g0.total_vram_gb


def _parse_nvidia_smi_all() -> list[GpuDevice]:
    """All NVIDIA GPUs from nvidia-smi (no PyTorch required)."""
    try:
        p = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if p.returncode != 0:
            return []
        out: list[GpuDevice] = []
        for raw in (p.stdout or "").strip().splitlines():
            line = raw.strip()
            if not line:
                continue
            parts = [x.strip() for x in line.split(",")]
            if len(parts) < 2:
                continue
            try:
                idx = int(parts[0])
            except Exception:
                idx = len(out)
            name = parts[1] if len(parts) > 1 else f"GPU {idx}"
            mem_mb = None
            if len(parts) > 2:
                try:
                    mem_mb = float(parts[2])
                except Exception:
                    mem_mb = None
            vram_b = int((mem_mb * 1024 * 1024)) if mem_mb is not None else 0
            out.append(
                GpuDevice(
                    index=idx,
                    name=name,
                    total_vram_bytes=max(vram_b, 0),
                )
            )
        return sorted(out, key=lambda g: g.index)
    except Exception:
        return []


def list_cuda_gpus() -> list[GpuDevice]:
    """
    Enumerate CUDA devices. Prefer PyTorch (names + VRAM + compute); fall back to nvidia-smi.
    """
    try:
        import torch

        if cuda_device_reported_by_torch():
            n = int(torch.cuda.device_count())
            out: list[GpuDevice] = []
            for i in range(max(0, n)):
                try:
                    name = str(torch.cuda.get_device_name(i))
                    props = torch.cuda.get_device_properties(i)
                    total_b = int(props.total_memory)
                    sm = int(getattr(props, "multi_processor_count", 0) or 0)
                    maj = int(getattr(props, "major", 0) or 0)
                    mino = int(getattr(props, "minor", 0) or 0)
                    clk = int(getattr(props, "clock_rate", 0) or 0)
                    out.append(
                        GpuDevice(
                            index=i,
                            name=name,
                            total_vram_bytes=total_b,
                            multiprocessor_count=sm,
                            major=maj,
                            minor=mino,
                            clock_rate_khz=clk,
                        )
                    )
                except Exception:
                    continue
            if out:
                return out
    except Exception:
        pass
    return _parse_nvidia_smi_all()


def vram_hungry_device_index(gpus: list[GpuDevice]) -> int:
    """Index of the GPU with the largest total VRAM (ties: lower index wins)."""
    if not gpus:
        return 0
    best_i = 0
    best_b = -1
    for g in gpus:
        if g.total_vram_bytes > best_b:
            best_b = g.total_vram_bytes
            best_i = g.index
    return best_i


def compute_preferred_device_index(gpus: list[GpuDevice]) -> int:
    """
    Heuristic "faster" GPU for LLM / compute: score = SM count × max(1, clock_kHz / 1e6).
    Ties: lower index. Not a benchmark.
    """
    if not gpus:
        return 0
    best_i = gpus[0].index
    best_s = -1.0
    for g in gpus:
        clk_mhz = max(1.0, float(g.clock_rate_khz) / 1000.0) if g.clock_rate_khz else 1000.0
        score = float(max(1, g.multiprocessor_count)) * clk_mhz
        if g.major > 0:
            score *= 1.0 + 0.01 * float(g.major * 10 + g.minor)
        if score > best_s:
            best_s = score
            best_i = g.index
    return best_i


def _torch_cuda_info() -> tuple[str | None, float | None]:
    try:
        import torch

        if not cuda_device_reported_by_torch():
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


def _subprocess_run_hidden(cmd: list[str], *, timeout: float = 12.0) -> subprocess.CompletedProcess:
    kw: dict[str, Any] = dict(args=cmd, capture_output=True, text=True, timeout=timeout)
    if os.name == "nt":
        try:
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        except Exception:
            pass
    return subprocess.run(**kw)


def _cpu_brand_clock_windows() -> tuple[str | None, float | None]:
    """
    Commercial CPU name + nominal max clock from WMI (Win32_Processor).

    ``MaxClockSpeed`` is in MHz (often BIOS nominal / turbo table entry — not live turbo).
    """
    try:
        ps_cmd = (
            "$p = Get-CimInstance Win32_Processor | Select-Object -First 1; "
            "if ($null -eq $p) { exit 2 }; "
            "$p.Name.Trim() + '|' + [string][int]$p.MaxClockSpeed"
        )
        r = _subprocess_run_hidden(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            timeout=15.0,
        )
        if r.returncode != 0:
            return None, None
        line = (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""
        if "|" not in line:
            return None, None
        name, _, mhz_s = line.partition("|")
        name = name.strip()
        if not name:
            return None, None
        try:
            mhz = float(mhz_s.strip())
        except ValueError:
            return name, None
        if mhz <= 0:
            return name, None
        return name, mhz / 1000.0
    except Exception:
        return None, None


def _cpu_brand_clock_linux_proc() -> tuple[str | None, float | None]:
    """``/proc/cpuinfo`` model name + max ``cpu MHz`` across online cores."""
    try:
        model: str | None = None
        mhz_vals: list[float] = []
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                ls = line.strip()
                if ls.lower().startswith("model name") and ":" in line:
                    model = line.split(":", 1)[1].strip() or model
                elif ls.lower().startswith("cpu mhz") and ":" in line:
                    try:
                        mhz_vals.append(float(line.split(":", 1)[1].strip()))
                    except ValueError:
                        pass
                elif ls.startswith("Hardware") and ":" in line:
                    model = model or line.split(":", 1)[1].strip()
        if not model and not mhz_vals:
            return None, None
        ghz = max(mhz_vals) / 1000.0 if mhz_vals else None
        return model, ghz
    except Exception:
        return None, None


def _cpu_brand_clock_darwin_sysctl() -> tuple[str | None, float | None]:
    """macOS ``machdep.cpu.brand_string`` + optional ``hw.cpufrequency_max`` (Hz → GHz)."""
    name: str | None = None
    try:
        r = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            name = (r.stdout or "").strip()
    except Exception:
        pass
    ghz: float | None = None
    for key in ("hw.cpufrequency_max", "machdep.cpu.core_frequency"):
        try:
            r2 = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, timeout=5)
            if r2.returncode != 0:
                continue
            hz_s = (r2.stdout or "").strip()
            if not hz_s or hz_s == "unknown":
                continue
            hz = float(hz_s)
            # sysctl reports Hz on Intel macs (e.g. 2_400_000_000); Apple Silicon often omits these keys.
            if hz >= 1e9:
                ghz = hz / 1e9
            elif hz >= 1e6:
                ghz = hz / 1e6
            elif hz >= 1e3:
                ghz = hz / 1e3
            if ghz is not None and ghz > 0:
                break
        except Exception:
            continue
    return name, ghz


def _format_cpu_display_line(*, fallback: str, friendly: str | None, clock_ghz: float | None) -> str:
    """
    Single UI line: friendly commercial name when known, else ``platform.processor()`` fallback,
    plus nominal clock when detected.
    """
    base = (friendly or "").strip() or fallback.strip() or "Unknown CPU"
    if clock_ghz is not None and clock_ghz > 0:
        return f"{base} · ~{clock_ghz:.2f} GHz max"
    return base


def get_hardware_info() -> HardwareInfo:
    os_name = f"{platform.system()} {platform.release()} ({platform.version()})"
    raw_cpu = platform.processor() or platform.machine() or "Unknown CPU"
    friendly: str | None = None
    clk_ghz: float | None = None
    try:
        sysname = platform.system()
        if sysname == "Windows":
            friendly, clk_ghz = _cpu_brand_clock_windows()
        elif sysname == "Linux":
            friendly, clk_ghz = _cpu_brand_clock_linux_proc()
        elif sysname == "Darwin":
            friendly, clk_ghz = _cpu_brand_clock_darwin_sysctl()
    except Exception:
        friendly, clk_ghz = None, None
    cpu = _format_cpu_display_line(fallback=raw_cpu, friendly=friendly, clock_ghz=clk_ghz)
    ram_gb = _get_ram_gb_windows() if os.name == "nt" else None
    if ram_gb is None:
        ram_gb = _get_ram_gb_psutil()

    gpus = list_cuda_gpus()
    gpu_name: str | None = None
    vram_gb: float | None = None
    gpu_names_all: str | None = None
    if gpus:
        gpu_names_all = ", ".join(f"{g.index}: {g.name}" for g in gpus)
        max_b = max(g.total_vram_bytes for g in gpus)
        vram_gb = float(max_b) / (1024**3)
        gpu_name = gpus[0].name if len(gpus) == 1 else f"{len(gpus)} GPUs (max {vram_gb:.1f} GB)"
    else:
        gpu_name, vram_gb = _parse_nvidia_smi()
        if gpu_name is None:
            tname, tvram = _torch_cuda_info()
            gpu_name = tname
            vram_gb = tvram

    return HardwareInfo(
        os=os_name,
        cpu=cpu,
        ram_gb=ram_gb,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        gpu_names_all=gpu_names_all,
    )


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
        if "moss" in rl and "voice" in rl:
            return "~ 8-12 GB+ VRAM (2B instruction TTS); CPU possible but very slow"
        if "xtts" in rl or "coqui" in rl:
            return "~ 4-6 GB VRAM"
        if "bark" in rl or "/bark" in rl:
            return "~ 8-12 GB VRAM"
        if "parler" in rl:
            return "~ 4-8 GB VRAM"
        return "CPU OK"

    if kind == "script":
        rl = rid.lower()
        if "midnight-miqu" in rl or "miqu-70" in rl:
            return "~ 40+ GB VRAM (70B, 4-bit target)"
        if "deepseek" in rl and "v3" in rl:
            return "~ 40-64+ GB GPU or multi-GPU (671B MoE; ~37B active/token); ~685B on disk, large RAM if offloading"
        if "fimbulvetr" in rl:
            return "~ 10-16 GB VRAM (11B)"
        if "qwen3" in rl and "14" in rl.replace(" ", ""):
            return "~ 12-20 GB VRAM (14B, 4-bit target)"
        if "abliterated" in rl and "8b" in rl.replace(" ", "").lower():
            return "~ 6-10 GB VRAM (8B, 4-bit target)"
        if spd == "fastest":
            return "~ 3-8 GB VRAM"
        if spd == "faster":
            return "~ 4-10 GB VRAM"
        return "~ 6-8 GB VRAM"

    if kind == "image":
        rl = rid.lower()
        if "stable-diffusion-3.5" in rl and "large-turbo" in rl:
            return "~ 8-12 GB VRAM"
        if "stable-diffusion-3.5" in rl and "large" in rl and "turbo" not in rl:
            return "~ 14-20 GB VRAM"
        if "stable-diffusion-3" in rl:
            return "~ 10-14 GB VRAM"
        if "flux" in rl and "1.1" in rl and "ultra" in rl:
            return "~ 12-20 GB VRAM (1.1 [pro] ultra; Hub access may be required)"
        if "flux" in rl and "schnell" in rl:
            return "~ 12-16 GB VRAM"
        if "flux" in rl and "dev" in rl:
            return "~ 16-24 GB VRAM"
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
        if "wan-ai" in rl or "wan2.2" in rl or ("/wan" in rl and "t2v" in rl):
            return "~ 12-16 GB VRAM"
        if "mochi" in rl:
            return "~ 10-14 GB VRAM"
        if "cogvideox-5b" in rl:
            return "~ 6-10 GB VRAM"
        if "cogvideox" in rl:
            return "~ 12-16 GB VRAM"
        if "hunyuanvideo" in rl:
            return "~ 16-24+ GB VRAM"
        if "ltx-2" in rl:
            return "~ 24-40+ GB VRAM at 4K-class settings (LTX-2; lower res/CPU offload may fit less)"
        if "ltx-video" in rl or ("lightricks/ltx" in rl and "ltx-2" not in rl):
            return "~ 10-14 GB VRAM"
        if "stable-video-diffusion" in rl:
            return "~ 8-12 GB VRAM"
        if "zeroscope" in rl:
            return "~ 6-8 GB VRAM"
        if "stable-diffusion-xl-base" in rl and "turbo" not in rl:
            return "~ 8-10 GB VRAM"
        if "sdxl-turbo" in rl or rl.endswith("sdxl-turbo"):
            return "~ 6-8 GB VRAM"
        if "stable-diffusion-v1-5" in rl or "v1-5" in rl:
            return "~ 4-6 GB VRAM"
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
        elif "stable-diffusion-3.5" in rid and "large-turbo" in rid:
            need_ok = 8.0
            need_ex = 12.0
            why = "SD3.5 Large Turbo (ADD) is a few-step 3.5-family checkpoint; still a frontier stack."
        elif "stable-diffusion-3.5" in rid and "large" in rid and "turbo" not in rid:
            need_ok = 14.0
            need_ex = 20.0
            why = "SD3.5 Large is a full 3.5 MMDiT stack."
        elif "stable-diffusion-3" in rid:
            need_ok = 10.0
            need_ex = 14.0
            why = "SD3/3.5-family models use multiple text encoders; heavier than SDXL Turbo class."
        elif "stable-diffusion-xl-base" in rid and "turbo" not in rid:
            need_ok = 10.0
            need_ex = 14.0
            why = "SDXL Base is heavier than SDXL Turbo."
        elif "flux" in rid and "1.1" in rid and "ultra" in rid:
            need_ok = 12.0
            need_ex = 20.0
            why = "FLUX.1.1 [pro] ultra (faster than dev-class for typical runs; BFL Pro stack)."
        elif "flux" in rid and "schnell" in rid:
            need_ok = 12.0
            need_ex = 16.0
            why = "FLUX.1 Schnell is a frontier-class transformer diffusion model."
        elif "flux" in rid and "dev" in rid:
            need_ok = 16.0
            need_ex = 24.0
            why = "FLUX.1-dev is VRAM-heavy."
        else:
            need_ok = 8.0
            need_ex = 10.0
            why = "Image diffusion (mid-range) expectation."
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
        elif "wan-ai" in rid or "wan2.2" in rid or ("t2v" in rid and "wan" in rid and "a14b" in rid):
            need_ok = 12.0
            need_ex = 18.0
            why = "Wan 2.2 14B-class T2V is large; 480P-style settings reduce peak VRAM."
        elif "mochi" in rid:
            need_ok = 10.0
            need_ex = 14.0
            why = "Mochi 1.5 T2V (Genmo); long clips; quantization offloads are common in community setups."
        elif "cogvideox-5b" in rid:
            need_ok = 6.0
            need_ex = 10.0
            why = "CogVideoX 5B is the lightest of the curated frontier T2V stack at modest resolutions."
        elif "cogvideox" in rid:
            need_ok = 12.0
            need_ex = 16.0
            why = "CogVideoX 2B-class stacks still need headroom for coherent clips."
        elif "hunyuanvideo" in rid:
            need_ok = 16.0
            need_ex = 24.0
            why = "HunyuanVideo is frontier-class; full settings want high VRAM."
        elif "ltx-2" in rid:
            need_ok = 24.0
            need_ex = 40.0
            why = "LTX-2 (19B-class audio-video T2V); native 4K presets are very VRAM-heavy."
        elif "ltx-video" in rid or ("lightricks/ltx" in rid and "ltx-2" not in rid):
            need_ok = 10.0
            need_ex = 14.0
            why = "LTX-Video runs at higher resolution than lighter T2V stacks."
        elif "stable-video-diffusion" in rid or "img2vid" in rid:
            need_ok = 10.0
            need_ex = 14.0
            why = "Image-to-video diffusion is VRAM-heavy."
        elif "zeroscope" in rid and ("30x448" in rid or "448x256" in rid):
            need_ok = 5.0
            need_ex = 8.0
            why = "ZeroScope 448×256 is lighter than the 576w variant."
        elif "zeroscope" in rid:
            need_ok = 6.0
            need_ex = 10.0
            why = "Text-to-video at 576w is moderate weight."
        elif "text-to-video-ms" in rid or "modelscope" in rid:
            need_ok = 8.0
            need_ex = 12.0
            why = "ModelScope 1.7B text-to-video is moderate weight at 256²."
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

    if k == "script":
        if "midnight-miqu" in rid or "miqu-70" in rid:
            need_ok = 32.0
            need_ex = 48.0
            why = "70B-class merged story models need very large VRAM (typically 4-bit on one GPU)."
        elif "deepseek" in rid and "v3" in rid:
            need_ok = 40.0
            need_ex = 64.0
            why = "DeepSeek-V3 671B MoE (~37B active per token); expect very large GPU or multi-GPU, TB-scale disk, heavy RAM for offload."
        elif "fimbulvetr" in rid:
            need_ok = 10.0
            need_ex = 16.0
            why = "Fimbulvetr 11B is heavier than 8B-class models."
        elif "qwen" in rid and "14" in rid.replace(" ", ""):
            need_ok = 12.0
            need_ex = 20.0
            why = "Qwen3 14B Instruct; 4-bit local target; heavier than 8B-class."
        elif "8b" in rid.replace(" ", "") or "abliterated" in rid:
            need_ok = 6.0
            need_ex = 10.0
            why = "8B-class instruct (e.g. legacy abliterated); 4-bit target."
        else:
            return rate_model_fit(kind=kind, speed=speed, vram_gb=vram_gb, ram_gb=ram_gb)

        if vram_gb >= need_ex:
            return "EXCELLENT", f"{why} VRAM looks comfortable."
        if vram_gb >= need_ok:
            return "OK", f"{why} Should run if the model is unloaded between pipeline stages."
        if vram_gb >= max(4.0, need_ok - 2.0):
            return "RISKY", f"{why} Tight headroom; may OOM or need CPU offload."
        return "NO_GPU", f"{why} Likely too little VRAM; generation may fail."

    # For voice, keep the existing heuristic (speed-based).
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
    if "moss" in rid and "voice" in rid:
        if vram_gb >= 10:
            return "OK", "MOSS-VoiceGenerator is large; this VRAM should be workable on GPU."
        if vram_gb >= 8:
            return "RISKY", "MOSS-VoiceGenerator may be tight; expect long runs or CPU fallback."
        return "RISKY", "MOSS is heavy; prefer a smaller TTS (e.g. Kokoro) on low VRAM."
    if "speecht5" in rid:
        if vram_gb >= 4:
            return "OK", "SpeechT5 should run."
        return "RISKY", "Little VRAM; prefer a lighter TTS (e.g. Kokoro) or CPU."
    return "EXCELLENT", "Lightweight TTS checkpoint."


_SCRIPT_SPEED_RANK = {"fastest": 0, "faster": 1, "slow": 2}

# Lower index = preferred when GPU fit is equal (SDXL Turbo default balance).
_IMAGE_PREF_ORDER: tuple[str, ...] = (
    "stabilityai/stable-diffusion-3.5-large-turbo",
    "black-forest-labs/flux.1-schnell",
    "black-forest-labs/flux.1.1-pro-ultra",
    "stabilityai/stable-diffusion-3.5-medium",
    "stabilityai/stable-diffusion-3.5-large",
    "black-forest-labs/flux.1-dev",
)

_MOTION_VIDEO_PREF_ORDER: tuple[str, ...] = (
    "thudm/cogvideox-5b",
    "genmo/mochi-1.5-final",
    "wan-ai/wan2.2-t2v-a14b-diffusers",
    "tencent/hunyuanvideo",
    "lightricks/ltx-2",
)

_VOICE_PREF_ORDER: tuple[str, ...] = (
    "hexgrad/Kokoro-82M",
    "OpenMOSS-Team/MOSS-VoiceGenerator",
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
    script_quant_modes: tuple[str, ...] = ()
    image_quant_modes: tuple[str, ...] = ()
    video_quant_modes: tuple[str, ...] = ()
    voice_quant_modes: tuple[str, ...] = ()


def rank_models_for_auto_fit(
    model_options: list[ModelOption],
    hw: HardwareInfo,
    *,
    app_settings: Any | None = None,
) -> AutoFitRanked:
    """
    Order curated models by fit for this machine: script (LLM), image (T2I), video (motion), voice (TTS).
    First entries are the strongest matches; the UI applies the first **enabled** row per combo.

    When ``app_settings`` is set and CUDA GPUs are detected, each kind uses **effective VRAM** for that
    role (Auto: LLM vs diffusion device; Single: pinned GPU) — see ``cuda_device_policy.effective_vram_gb_for_kind``.
    """
    ram = hw.ram_gb

    def _vram(kind: str) -> float | None:
        if app_settings is not None:
            try:
                from src.util.cuda_device_policy import effective_vram_gb_for_kind

                gpus = list_cuda_gpus()
                if gpus:
                    return effective_vram_gb_for_kind(kind, gpus, app_settings)
            except Exception:
                pass
        return hw.vram_gb

    vram_script = _vram("script")
    vram_image = _vram("image")
    vram_video = _vram("video")
    vram_voice = _vram("voice")

    script_opts = [o for o in model_options if o.kind == "script"]
    image_opts = [o for o in model_options if o.kind == "image"]
    video_opts = [o for o in model_options if o.kind == "video"]
    voice_opts = [o for o in model_options if o.kind == "voice"]

    def script_key(o: ModelOption) -> tuple[float, float]:
        m, _ = rate_model_fit_for_repo(
            kind="script",
            speed=o.speed,
            repo_id=o.repo_id,
            vram_gb=vram_script,
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
            vram_gb=vram_image,
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
            vram_gb=vram_video,
            ram_gb=ram,
        )
        rk = float(marker_rank(m))
        pref = float(_motion_video_pref_index(o.repo_id))
        return (-rk, pref)

    def voice_key(o: ModelOption) -> tuple[float, float]:
        m, _ = voice_fit_marker(o.repo_id, vram_voice)
        rk = float(marker_rank(m))
        pref = float(_voice_pref_index(o.repo_id))
        return (-rk, pref)

    script_sorted = sorted(script_opts, key=script_key)
    image_sorted = sorted(image_opts, key=image_key)
    video_sorted = sorted(video_opts, key=video_key)
    voice_sorted = sorted(voice_opts, key=voice_key)

    script_ids = tuple(o.repo_id for o in script_sorted)
    image_ids = tuple(o.repo_id for o in image_sorted)
    video_ids = tuple(o.repo_id for o in video_sorted)
    voice_ids = tuple(o.repo_id for o in voice_sorted)

    def _auto_q(kind: str, rid: str, vram: float | None) -> str:
        try:
            from src.models.quantization import pick_auto_mode

            # CUDA device visible or VRAM heuristic from hardware probes.
            cuda_ok = cuda_device_reported_by_torch() or (vram is not None and vram > 0)
            return str(pick_auto_mode(role=kind, repo_id=rid, vram_gb=vram, cuda_ok=cuda_ok))
        except Exception:
            return "auto"

    script_q = tuple(_auto_q("script", rid, vram_script) for rid in script_ids)
    image_q = tuple(_auto_q("image", rid, vram_image) for rid in image_ids)
    video_q = tuple(_auto_q("video", rid, vram_video) for rid in video_ids)
    voice_q = tuple(_auto_q("voice", rid, vram_voice) for rid in voice_ids)

    by_repo = {o.repo_id: o for o in model_options}
    gpu_lbl = (hw.gpu_names_all or hw.gpu_name) or "GPU unknown"
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
        script_quant_modes=script_q,
        image_quant_modes=image_q,
        video_quant_modes=video_q,
        voice_quant_modes=voice_q,
        log_summary=log_summary,
    )

