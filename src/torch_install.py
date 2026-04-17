"""
Install PyTorch builds that match the machine: CUDA wheels when an NVIDIA GPU is
likely present (Windows/Linux), CPU wheels otherwise, and default PyPI wheels on
macOS (Metal/MPS). Intended to run before ``pip install -r requirements.txt``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Default CUDA 12.4 wheel repo (PyTorch 2.4+); aligns with common driver support.
_PYTORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu124"
_PYTORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"

_TORCH_PKGS = ["torch", "torchvision", "torchaudio"]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def nvidia_gpu_likely_available() -> bool:
    """Best-effort: True if an NVIDIA GPU is expected (nvidia-smi or WMI on Windows)."""
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            r = subprocess.run([smi, "-L"], capture_output=True, text=True, timeout=10)
            out = (r.stdout or "").strip()
            if r.returncode == 0 and out and ("GPU" in out or "UUID" in out):
                return True
        except (OSError, subprocess.SubprocessError):
            pass
    if sys.platform == "win32":
        try:
            r = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "Name"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            out = (r.stdout or "").upper()
            if r.returncode == 0 and "NVIDIA" in out:
                return True
        except (OSError, subprocess.SubprocessError):
            pass
    return False


def _installed_torch_is_cuda_build() -> bool | None:
    """None if torch missing / unreadable; True if built with CUDA; False if CPU-only."""
    try:
        import torch

        return bool(torch.version.cuda)
    except Exception:
        return None


def pip_python(explicit: str | None) -> list[str]:
    if explicit:
        return [explicit]
    return [sys.executable]


def build_pytorch_install_cmd(
    *,
    python_exe: str | None = None,
    upgrade: bool = True,
) -> tuple[list[str], str]:
    """
    Returns argv for subprocess and a short human description.
    """
    exe = pip_python(python_exe)
    base = exe + ["-m", "pip", "install"]
    if upgrade:
        base.append("--upgrade")

    if sys.platform == "darwin":
        # Apple Silicon / Intel: official builds on PyPI (MPS when available).
        cmd = base + _TORCH_PKGS
        return cmd, "PyPI (macOS — Metal/MPS when supported)"

    if nvidia_gpu_likely_available():
        cmd = base + ["--index-url", _PYTORCH_CUDA_INDEX] + _TORCH_PKGS
        return cmd, f"NVIDIA CUDA (index {_PYTORCH_CUDA_INDEX})"

    cmd = base + ["--index-url", _PYTORCH_CPU_INDEX] + _TORCH_PKGS
    return cmd, f"CPU-only (index {_PYTORCH_CPU_INDEX})"


def run_subprocess(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    except subprocess.TimeoutExpired:
        return 124, "Timeout while running pip (exceeded 2h)."
    except Exception as e:
        return 1, str(e)
    out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    return p.returncode, out


def install_pytorch_for_hardware(
    *,
    python_exe: str | None = None,
    upgrade: bool = True,
    force_cuda_if_applicable: bool = False,
) -> tuple[int, str]:
    """
    Install torch / torchvision / torchaudio for this OS + GPU.

    If ``force_cuda_if_applicable`` and an NVIDIA GPU is detected but the
    current install is a CPU-only build, uninstall torch* first then reinstall
    from the CUDA index.
    """
    if sys.platform != "darwin" and nvidia_gpu_likely_available() and force_cuda_if_applicable:
        built = _installed_torch_is_cuda_build()
        if built is False:
            exe = pip_python(python_exe)
            uninstall = exe + ["-m", "pip", "uninstall", "-y"] + _TORCH_PKGS
            code, out = run_subprocess(uninstall)
            if code != 0:
                return code, out

    cmd, desc = build_pytorch_install_cmd(python_exe=python_exe, upgrade=upgrade)
    code, out = run_subprocess(cmd)
    header = f"# PyTorch install ({desc})\n# Command: {' '.join(cmd)}\n\n"
    return code, header + out


def install_requirements_runtime(
    *,
    python_exe: str | None = None,
    requirements_path: Path | None = None,
) -> tuple[int, str]:
    """pip install -r requirements.txt (no ``torch`` line — torch installed separately)."""
    root = repo_root()
    req = requirements_path or (root / "requirements.txt")
    if not req.is_file():
        return 1, f"Missing {req}"
    exe = pip_python(python_exe)
    cmd = exe + ["-m", "pip", "install", "-r", str(req)]
    return run_subprocess(cmd)


def install_pytorch_then_rest(
    *,
    python_exe: str | None = None,
    force_cuda_if_applicable: bool = True,
) -> tuple[int, str]:
    """Install matching PyTorch, then ``pip install -r requirements.txt``."""
    chunks: list[str] = []
    c1, o1 = install_pytorch_for_hardware(
        python_exe=python_exe, upgrade=True, force_cuda_if_applicable=force_cuda_if_applicable
    )
    chunks.append(o1)
    if c1 != 0:
        return c1, "\n\n".join(chunks)
    c2, o2 = install_requirements_runtime(python_exe=python_exe)
    chunks.append(o2)
    return c2, "\n\n".join(chunks)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Install PyTorch matched to CPU/GPU, optionally the rest of Aquaduct deps.")
    p.add_argument(
        "--with-rest",
        action="store_true",
        help="After PyTorch, run pip install -r requirements.txt",
    )
    p.add_argument("--python", default=None, help="Python executable to use (default: sys.executable)")
    p.add_argument(
        "--no-force-cuda-switch",
        action="store_true",
        help="Do not uninstall CPU-only torch when NVIDIA GPU is present.",
    )
    args = p.parse_args(argv)

    force_cuda = not args.no_force_cuda_switch
    if args.with_rest:
        code, out = install_pytorch_then_rest(python_exe=args.python, force_cuda_if_applicable=force_cuda)
    else:
        code, out = install_pytorch_for_hardware(
            python_exe=args.python, upgrade=True, force_cuda_if_applicable=force_cuda
        )
    print(out)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
