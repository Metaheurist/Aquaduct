"""
Install PyTorch builds that match the machine: CUDA wheels when an NVIDIA GPU is
likely present (Windows/Linux), CPU wheels otherwise, and default PyPI wheels on
macOS (Metal/MPS). Intended to run before ``pip install -r requirements.txt``.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
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


def _inject_pip_progress_bar_on(cmd: list[str]) -> list[str]:
    """Ask pip to emit progress (helps when stdout is not a TTY)."""
    out = list(cmd)
    if "--progress-bar" in out:
        return out
    for i in range(len(out) - 2):
        if out[i] == "-m" and out[i + 1] == "pip" and out[i + 2] == "install":
            out.insert(i + 3, "--progress-bar")
            out.insert(i + 4, "on")
            break
    return out


def _flush_stream_buffer(buf: str, on_segment: Callable[[str], None] | None) -> str:
    """Split pip output on \\r or \\n so carriage-return progress lines are visible."""
    if not on_segment:
        return buf
    while True:
        m = re.search(r"[\r\n]", buf)
        if not m:
            break
        seg = buf[: m.start()].strip()
        buf = buf[m.end() :]
        if seg:
            on_segment(seg)
    return buf


def run_subprocess_streaming(
    cmd: list[str],
    on_line: Callable[[str], None] | None = None,
    *,
    timeout_s: float = 7200.0,
) -> tuple[int, str]:
    """
    Run a command and stream merged stdout/stderr. Splits on ``\\r`` and ``\\n`` so
    pip's in-place progress (same-line updates) still yields segments for the UI.
    """
    raw_parts: list[str] = []
    buf = ""
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=0,
        )
        if p.stdout is None:
            return 1, ""
        try:
            while True:
                chunk = p.stdout.read(4096)
                if not chunk:
                    break
                raw_parts.append(chunk)
                buf = _flush_stream_buffer(buf + chunk, on_line)
            tail = buf.strip()
            if tail and on_line:
                on_line(tail)
        finally:
            try:
                p.stdout.close()
            except Exception:
                pass
        rc = p.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            p.kill()
        except Exception:
            pass
        return 124, "".join(raw_parts) + "\nTimeout while running pip (exceeded 2h)."
    except Exception as e:
        return 1, "".join(raw_parts) + f"\n{e!s}"
    return int(rc), "".join(raw_parts)


def pip_download_percent(line: str) -> int | None:
    """
    Best-effort: parse a 0–100 download/install percentage from a pip or tqdm-style line.
    Returns None if no percentage is found.
    """
    s = (line or "").strip()
    if not s:
        return None
    for pat in (
        r"\b(\d{1,3})%",
        r"\|\s*(\d{1,3})%\s*\|",
        r"(\d{1,3})%\s*\|",
    ):
        m = re.search(pat, s)
        if m:
            v = int(m.group(1))
            if 0 <= v <= 100:
                return v
    return None


def pip_line_hint(line: str) -> str | None:
    """
    Best-effort: extract a short \"what pip is doing\" string for UI status.
    """
    s = (line or "").strip()
    if not s or s.startswith("WARNING:") and len(s) > 220:
        return None
    # Collecting package==1.2 or Collecting package
    m = re.match(r"Collecting\s+(\S+)", s)
    if m:
        pkg = m.group(1).split("[", 1)[0].strip()
        return f"Collecting {pkg}"
    # e.g. "Downloading https://.../torch-....whl (2532.3 MB)" — huge wheels; log often goes quiet for a long time
    m = re.search(r"Downloading\s+\S+\s+\(([\d.]+)\s*(MB|GB)\)\s*$", s)
    if m:
        return (
            f"Downloading ~{m.group(1)} {m.group(2)} — active; pip may print nothing for many minutes on large files"
        )
    m = re.match(r"Downloading\s+(\S+)", s)
    if m:
        return f"Downloading {m.group(1)[:80]}"
    m = re.match(r"Using cached\s+(\S+)", s)
    if m:
        return f"Using cached {m.group(1).split()[0][:80]}"
    if s.startswith("Installing collected packages:"):
        tail = s.replace("Installing collected packages:", "").strip()
        return f"Installing {tail[:100]}{'…' if len(tail) > 100 else ''}"
    m = re.search(r"Requirement already satisfied:\s*(\S+)", s)
    if m:
        return f"Already satisfied: {m.group(1).split()[0][:60]}"
    if "Successfully installed" in s:
        return s[:160]
    if s.startswith("ERROR:") or "error:" in s.lower():
        return s[:200]
    return None


def _run_pip(cmd: list[str], on_line: Callable[[str], None] | None) -> tuple[int, str]:
    if on_line:
        return run_subprocess_streaming(_inject_pip_progress_bar_on(cmd), on_line)
    return run_subprocess(cmd)


def install_pytorch_for_hardware(
    *,
    python_exe: str | None = None,
    upgrade: bool = True,
    force_cuda_if_applicable: bool = False,
    on_line: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    """
    Install torch / torchvision / torchaudio for this OS + GPU.

    If ``force_cuda_if_applicable`` and an NVIDIA GPU is detected but the
    current install is a CPU-only build, uninstall torch* first then reinstall
    from the CUDA index.

    ``on_line`` receives each output line (pip stdout) for live UI progress.
    """
    if sys.platform != "darwin" and nvidia_gpu_likely_available() and force_cuda_if_applicable:
        built = _installed_torch_is_cuda_build()
        if built is False:
            exe = pip_python(python_exe)
            uninstall = exe + ["-m", "pip", "uninstall", "-y"] + _TORCH_PKGS
            code, out = _run_pip(uninstall, on_line)
            if code != 0:
                return code, out

    cmd, desc = build_pytorch_install_cmd(python_exe=python_exe, upgrade=upgrade)
    code, out = _run_pip(cmd, on_line)
    header = f"# PyTorch install ({desc})\n# Command: {' '.join(cmd)}\n\n"
    return code, header + out


def install_requirements_runtime(
    *,
    python_exe: str | None = None,
    requirements_path: Path | None = None,
    on_line: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    """pip install -r requirements.txt (no ``torch`` line — torch installed separately)."""
    root = repo_root()
    req = requirements_path or (root / "requirements.txt")
    if not req.is_file():
        return 1, f"Missing {req}"
    exe = pip_python(python_exe)
    cmd = exe + ["-m", "pip", "install", "-r", str(req)]
    return _run_pip(cmd, on_line)


def install_pytorch_then_rest(
    *,
    python_exe: str | None = None,
    force_cuda_if_applicable: bool = True,
    on_line: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    """Install matching PyTorch, then ``pip install -r requirements.txt``."""
    chunks: list[str] = []
    c1, o1 = install_pytorch_for_hardware(
        python_exe=python_exe,
        upgrade=True,
        force_cuda_if_applicable=force_cuda_if_applicable,
        on_line=on_line,
    )
    chunks.append(o1)
    if c1 != 0:
        return c1, "\n\n".join(chunks)
    c2, o2 = install_requirements_runtime(python_exe=python_exe, on_line=on_line)
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
