"""
Install PyTorch builds that match the machine: CUDA wheels when an NVIDIA GPU is
likely present (Windows/Linux), CPU wheels otherwise, and default PyPI wheels on
macOS (Metal/MPS). Intended to run before ``pip install -r requirements.txt``.

CUDA wheel index is chosen automatically: ``cu128`` for Blackwell / RTX 50-series
(compute capability 12+ or name match), otherwise ``cu124`` for typical consumer GPUs.
Override with env ``AQUADUCT_PYTORCH_CUDA_INDEX=cu124|cu128`` or a full index URL.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from src.util.cuda_capabilities import cuda_device_reported_by_torch

# CUDA wheel repos (see https://pytorch.org/get-started/locally/).
# cu124: most NVIDIA GPUs through Ada (sm <= 9.x).
# cu128: CUDA 12.8+ builds with Blackwell (sm 12.x) kernels, e.g. RTX 50-series.
_PYTORCH_CUDA_INDEX_CU124 = "https://download.pytorch.org/whl/cu124"
_PYTORCH_CUDA_INDEX_CU128 = "https://download.pytorch.org/whl/cu128"
_PYTORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"

_TORCH_PKGS = ["torch", "torchvision", "torchaudio"]

# Windows: pip download each index into DEST/<name>/ (current interpreter ABI).
# Extend if PyTorch adds new CUDA lines (see https://pytorch.org/get-started/locally/).
_PYTORCH_WINDOWS_WHEEL_VARIANTS: tuple[tuple[str, str], ...] = (
    ("cu128", "https://download.pytorch.org/whl/cu128"),
    ("cu124", "https://download.pytorch.org/whl/cu124"),
    ("cu121", "https://download.pytorch.org/whl/cu121"),
    ("cu118", "https://download.pytorch.org/whl/cu118"),
    ("cpu", "https://download.pytorch.org/whl/cpu"),
)

# RTX 50-series (Blackwell consumer): PyTorch needs cu128; name-based fallback when smi has no compute_cap.
_RTX_BLACKWELL_NAME_RE = re.compile(r"\bRTX\s*5\d{3}\b", re.IGNORECASE)


def repo_root() -> Path:
    """Root of the Aquaduct tree (directory with ``requirements.txt`` and ``src/``).

    Historically ``parents[1]`` was used by mistake — from ``src/models/torch_install.py``
    that resolves to ``src/``, so ``requirements.txt`` was never found.
    """
    if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None):
        base = Path(sys._MEIPASS)  # type: ignore[arg-type]
        if (base / "requirements.txt").is_file():
            return base
    here = Path(__file__).resolve()
    return here.parents[2]


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


def _pytorch_cuda_index_from_env() -> str | None:
    """
    Optional override: ``AQUADUCT_PYTORCH_CUDA_INDEX=cu124``, ``cu128``, or full ``https://...`` URL.
    """
    raw = (os.environ.get("AQUADUCT_PYTORCH_CUDA_INDEX") or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower in ("cu124", "cu128", "cu121", "cu118"):
        return f"https://download.pytorch.org/whl/{lower}"
    if raw.startswith("https://"):
        return raw
    return None


def _torch_reports_blackwell_or_newer() -> bool | None:
    """True if installed torch sees CUDA sm 12+; None if torch missing or no CUDA."""
    try:
        import torch
    except Exception:
        return None

    if not cuda_device_reported_by_torch():
        return None
    try:
        major, _minor = torch.cuda.get_device_capability(0)
    except Exception:
        return None
    return major >= 12


def _nvidia_smi_compute_capability_major() -> int | None:
    """First GPU's compute capability major from nvidia-smi, or None."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        r = subprocess.run(
            [smi, "--query-gpu=compute_cap", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0 or not (r.stdout or "").strip():
            return None
        first = (r.stdout or "").strip().splitlines()[0].strip()
        if "." in first:
            return int(first.split(".", 1)[0].strip())
        return int(first)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _nvidia_gpu_marketing_names() -> list[str]:
    """GPU product strings from nvidia-smi -L and Windows WMI (best-effort)."""
    names: list[str] = []
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            r = subprocess.run([smi, "-L"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout:
                for line in (r.stdout or "").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    # e.g. GPU 0: NVIDIA GeForce RTX 5060 (UUID: ...)
                    if ":" in line:
                        part = line.split(":", 2)
                        if len(part) >= 2:
                            names.append(part[1].split("(")[0].strip())
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
            if r.returncode == 0 and r.stdout:
                for line in r.stdout.splitlines():
                    t = line.strip()
                    if t and t.lower() != "name":
                        names.append(t)
        except (OSError, subprocess.SubprocessError):
            pass
    return names


def prefer_pytorch_cu128_index() -> bool:
    """
    True when this machine likely needs the cu128 wheel (Blackwell sm_12x / RTX 50-series).

    Uses installed torch (if any), then nvidia-smi compute_cap, then GPU name heuristic.
    For ``AQUADUCT_PYTORCH_CUDA_INDEX``, see ``pytorch_cuda_wheel_index_url()`` instead.
    """
    t = _torch_reports_blackwell_or_newer()
    if t is True:
        return True
    if t is False:
        return False
    smi_maj = _nvidia_smi_compute_capability_major()
    if smi_maj is not None:
        return smi_maj >= 12
    for n in _nvidia_gpu_marketing_names():
        if _RTX_BLACKWELL_NAME_RE.search(n):
            return True
    return False


def pytorch_cuda_wheel_index_url() -> str:
    """PyTorch ``--index-url`` for pip when an NVIDIA GPU is used (non-macOS)."""
    env = _pytorch_cuda_index_from_env()
    if env is not None:
        return env
    return _PYTORCH_CUDA_INDEX_CU128 if prefer_pytorch_cu128_index() else _PYTORCH_CUDA_INDEX_CU124


def _installed_torch_is_cuda_build() -> bool | None:
    """None if torch missing / unreadable; True if built with CUDA; False if CPU-only."""
    try:
        import torch

        return bool(torch.version.cuda)
    except Exception:
        return None


def _windows_branded_interpreter(role: str) -> str:
    """
    Windows Task Manager labels processes by the ``.exe`` file name, so every child
    ``python.exe`` looks identical. Copy the real interpreter to
    ``aquaduct-pip-<role>.exe`` in the same directory (e.g. venv ``Scripts/``) and use
    that for pip subprocesses so each role gets a distinct name in Task Manager.
    """
    exe = Path(sys.executable).resolve()
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "", role).strip() or "pip"
    branded = exe.parent / f"aquaduct-pip-{safe}.exe"
    try:
        if not branded.is_file() or exe.stat().st_mtime > branded.stat().st_mtime:
            shutil.copy2(exe, branded)
    except OSError:
        return str(exe)
    return str(branded)


def pip_python(explicit: str | None, *, role: str = "pip") -> list[str]:
    """
    Interpreter argv0 for ``python -m pip ...``. On Windows, uses a per-``role``
    branded copy of ``python.exe`` so Task Manager can distinguish pip workers.
    """
    if explicit:
        return [explicit]
    if sys.platform == "win32":
        return [_windows_branded_interpreter(role)]
    return [sys.executable]


def build_pytorch_install_cmd(
    *,
    python_exe: str | None = None,
    upgrade: bool = True,
) -> tuple[list[str], str]:
    """
    Returns argv for subprocess and a short human description.
    """
    exe = pip_python(python_exe, role="torch")
    base = exe + ["-m", "pip", "install"]
    if upgrade:
        base.append("--upgrade")

    if sys.platform == "darwin":
        # Apple Silicon / Intel: official builds on PyPI (MPS when available).
        cmd = base + _TORCH_PKGS
        return cmd, "PyPI (macOS - Metal/MPS when supported)"

    if nvidia_gpu_likely_available():
        idx = pytorch_cuda_wheel_index_url()
        if "cu128" in idx:
            hint = "NVIDIA CUDA 12.8+ wheels (cu128 - Blackwell / RTX 50-series when detected)"
        elif "cu124" in idx:
            hint = "NVIDIA CUDA (cu124)"
        else:
            hint = f"NVIDIA CUDA (index {idx})"
        cmd = base + ["--index-url", idx] + _TORCH_PKGS
        return cmd, hint

    cmd = base + ["--index-url", _PYTORCH_CPU_INDEX] + _TORCH_PKGS
    return cmd, f"CPU-only (index {_PYTORCH_CPU_INDEX})"


def format_pytorch_pip_cli(cmd: list[str]) -> str:
    """Shell-friendly single string for logging / error text (Windows-aware)."""
    if sys.platform == "win32":
        return subprocess.list2cmdline(cmd)
    import shlex

    return shlex.join(cmd)


def pytorch_cpu_wheel_with_nvidia_gpu_present() -> bool:
    """
    True when the machine reports an NVIDIA GPU (driver) but the installed
    ``torch`` wheel is CPU-only (no ``torch.version.cuda``).

    macOS is excluded — Aquaduct uses PyPI Metal builds there, not NVIDIA CUDA wheels.
    """
    if sys.platform == "darwin":
        return False
    if not nvidia_gpu_likely_available():
        return False
    built = _installed_torch_is_cuda_build()
    return built is False


def cuda_torch_required_message_for_nvidia_host() -> str:
    """User-facing blocker text + example ``pip`` line for CPU-only PyTorch on NVIDIA PCs."""
    cmd, hint = build_pytorch_install_cmd(upgrade=True)
    cli = format_pytorch_pip_cli(cmd)
    return (
        "An NVIDIA GPU was detected on this PC, but the active Python environment has "
        "CPU-only PyTorch (no CUDA). Local inference will not use the GPU.\n\n"
        f"Install the CUDA-enabled build ({hint}). Example:\n  {cli}\n\n"
        "You can also use **Help → Install dependencies** (or reinstall torch with the CUDA index).\n\n"
        "Advanced: set AQUADUCT_ALLOW_CPU_TORCH_WITH_NVIDIA=1 to suppress this block and "
        "allow intentionally slow CPU runs."
    )


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


class PipSubprocessRef:
    """
    Holds the active :class:`subprocess.Popen` for a streaming pip run so the UI can
    :meth:`kill` the process when the user cancels.
    """

    __slots__ = ("proc",)

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None

    def kill(self) -> None:
        p = self.proc
        if p is None:
            return
        try:
            if p.poll() is None:
                p.kill()
        except OSError:
            pass


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
    on_first_pip_output: Callable[[str], None] | None = None,
    subprocess_ref: PipSubprocessRef | None = None,
    timeout_s: float = 7200.0,
) -> tuple[int, str]:
    """
    Run a command and stream merged stdout/stderr. Splits on ``\\r`` and ``\\n`` so
    pip's in-place progress (same-line updates) still yields segments for the UI.

    ``on_first_pip_output`` is called once with the first non-empty segment read from
    the subprocess **stream** (not the synthetic ``$`` / ``#`` lines), so the UI can
    confirm pip actually wrote to stdout.

    ``subprocess_ref`` is updated with the running :class:`subprocess.Popen` so the UI
    can terminate it on cancel.
    """
    raw_parts: list[str] = []
    buf = ""
    first_stream_line = True

    def _relay_stream(seg: str) -> None:
        nonlocal first_stream_line
        if not seg or not seg.strip():
            return
        if first_stream_line:
            first_stream_line = False
            if on_first_pip_output:
                try:
                    on_first_pip_output(seg)
                except Exception:
                    pass
        if on_line:
            on_line(seg)

    # Without this, ``python -m pip`` uses block-buffered stdout when piped and the UI
    # stays empty until ~8 KiB of output or the process exits.
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    try:
        if on_line:
            shown = " ".join(cmd)
            if len(shown) > 480:
                shown = shown[:477] + "..."
            on_line(f"$ {shown}")
    except Exception:
        pass
    p: subprocess.Popen | None = None
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=0,
            env=env,
        )
        if subprocess_ref is not None:
            subprocess_ref.proc = p
        if p.stdout is None:
            return 1, ""
        try:
            if on_line:
                on_line(
                    "# pip process started - resolving the index and downloading wheels can take many minutes; "
                    "new lines may appear only after metadata resolves or a chunk finishes."
                )
            while True:
                chunk = p.stdout.read(4096)
                if not chunk:
                    break
                raw_parts.append(chunk)
                buf = _flush_stream_buffer(buf + chunk, _relay_stream)
            tail = buf.strip()
            if tail:
                _relay_stream(tail)
        finally:
            try:
                p.stdout.close()
            except Exception:
                pass
        rc = p.wait(timeout=timeout_s)
        return int(rc), "".join(raw_parts)
    except subprocess.TimeoutExpired:
        if p is not None:
            try:
                p.kill()
            except Exception:
                pass
        return 124, "".join(raw_parts) + "\nTimeout while running pip (exceeded 2h)."
    except Exception as e:
        return 1, "".join(raw_parts) + f"\n{e!s}"
    finally:
        if subprocess_ref is not None:
            subprocess_ref.proc = None


def pip_download_percent(line: str) -> int | None:
    """
    Best-effort: parse a 0-100 download/install percentage from a pip or tqdm-style line.
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
    if s.startswith("# pip process started"):
        return "pip is running - CUDA wheels are large; the log may stay quiet for a long time"
    if s.startswith("# Preparing PyTorch install"):
        return "Preparing PyTorch install..."
    if s.startswith("# Checking whether an existing torch"):
        return "Checking torch build (import can take a while)..."
    if s.startswith("# Installing packages from requirements"):
        return "Installing requirements.txt..."
    # Collecting package==1.2 or Collecting package
    m = re.match(r"Collecting\s+(\S+)", s)
    if m:
        pkg = m.group(1).split("[", 1)[0].strip()
        return f"Collecting {pkg}"
    # e.g. "Downloading https://.../torch-....whl (2532.3 MB)" - huge wheels; log often goes quiet for a long time
    m = re.search(r"Downloading\s+\S+\s+\(([\d.]+)\s*(MB|GB)\)\s*$", s)
    if m:
        return (
            f"Downloading ~{m.group(1)} {m.group(2)} - active; pip may print nothing for many minutes on large files"
        )
    m = re.match(r"Downloading\s+(\S+)", s)
    if m:
        return f"Downloading {m.group(1)[:80]}"
    m = re.match(r"Using cached\s+(\S+)", s)
    if m:
        return f"Using cached {m.group(1).split()[0][:80]}"
    if s.startswith("Installing collected packages:"):
        tail = s.replace("Installing collected packages:", "").strip()
        return f"Installing {tail[:100]}{'...' if len(tail) > 100 else ''}"
    m = re.search(r"Requirement already satisfied:\s*(\S+)", s)
    if m:
        return f"Already satisfied: {m.group(1).split()[0][:60]}"
    if "Successfully installed" in s:
        return s[:160]
    if s.startswith("ERROR:") or "error:" in s.lower():
        return s[:200]
    return None


def _run_pip(
    cmd: list[str],
    on_line: Callable[[str], None] | None,
    on_first_pip_output: Callable[[str], None] | None = None,
    subprocess_ref: PipSubprocessRef | None = None,
) -> tuple[int, str]:
    if on_line:
        return run_subprocess_streaming(
            _inject_pip_progress_bar_on(cmd),
            on_line,
            on_first_pip_output=on_first_pip_output,
            subprocess_ref=subprocess_ref,
        )
    return run_subprocess(cmd)


def install_pytorch_for_hardware(
    *,
    python_exe: str | None = None,
    upgrade: bool = True,
    force_cuda_if_applicable: bool = False,
    on_line: Callable[[str], None] | None = None,
    on_first_pip_output: Callable[[str], None] | None = None,
    subprocess_ref: PipSubprocessRef | None = None,
) -> tuple[int, str]:
    """
    Install torch / torchvision / torchaudio for this OS + GPU.

    If ``force_cuda_if_applicable`` and an NVIDIA GPU is detected but the
    current install is a CPU-only build, uninstall torch* first then reinstall
    from the CUDA index.

    ``on_line`` receives each output line (pip stdout) for live UI progress.
    ``on_first_pip_output`` is invoked once per pip subprocess when pip first
    prints to stdout (confirms the install is really talking to pip).
    ``subprocess_ref`` tracks the active pip process for UI cancellation.
    """
    if on_line:
        on_line("# Preparing PyTorch install...")
    if sys.platform != "darwin" and nvidia_gpu_likely_available() and force_cuda_if_applicable:
        if on_line:
            on_line("# Checking whether an existing torch is CUDA or CPU-only (may import torch; first load can take a while)...")
        built = _installed_torch_is_cuda_build()
        if built is False:
            exe = pip_python(python_exe, role="uninstall")
            if on_line:
                on_line(
                    "# Removing any existing torch / torchvision / torchaudio "
                    "(separate uninstall per package; 'Skipping' means it was not installed - "
                    "we still install all three together next)."
                )
            for pkg in _TORCH_PKGS:
                uninstall_one = exe + ["-m", "pip", "uninstall", "-y", pkg]
                if on_line:
                    on_line(f"# pip uninstall -y {pkg}")
                code_u, _frag = _run_pip(uninstall_one, on_line, on_first_pip_output, subprocess_ref)
                if code_u != 0 and on_line:
                    on_line(
                        f"# Uninstall exited {code_u} for {pkg}; continuing - "
                        "install step still requests torch, torchvision, and torchaudio."
                    )
            if on_line:
                on_line("# pip install torch torchvision torchaudio together (explicit - none omitted)")

    cmd, desc = build_pytorch_install_cmd(python_exe=python_exe, upgrade=upgrade)
    if on_line:
        on_line(f"# PyTorch install - {desc}")
    code, out = _run_pip(cmd, on_line, on_first_pip_output, subprocess_ref)
    header = f"# PyTorch install ({desc})\n# Command: {' '.join(cmd)}\n\n"
    return code, header + out


def install_requirements_runtime(
    *,
    python_exe: str | None = None,
    requirements_path: Path | None = None,
    on_line: Callable[[str], None] | None = None,
    on_first_pip_output: Callable[[str], None] | None = None,
    subprocess_ref: PipSubprocessRef | None = None,
) -> tuple[int, str]:
    """pip install -r requirements.txt (no ``torch`` line - torch installed separately)."""
    root = repo_root()
    req = requirements_path or (root / "requirements.txt")
    if not req.is_file():
        return 1, f"Missing {req}"
    if on_line:
        on_line("# Installing packages from requirements.txt...")
    exe = pip_python(python_exe, role="reqs")
    cmd = exe + ["-m", "pip", "install", "-r", str(req)]
    return _run_pip(cmd, on_line, on_first_pip_output, subprocess_ref)


def download_all_windows_torch_wheels(
    dest: Path,
    *,
    python_exe: str | None = None,
    on_line: Callable[[str], None] | None = None,
    on_variant_start: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    """
    Download wheel files for ``torch`` / ``torchvision`` / ``torchaudio`` from each
    official PyTorch index into ``dest/<variant>/`` (no install). Uses the same Python
    ABI as ``python_exe`` (or the running interpreter). Windows only.

    PyPI is used as ``--extra-index-url`` so CUDA metapackages (e.g. ``nvidia-*``) resolve.
    A variant may fail if that index no longer publishes builds for your Python version;
    check the combined log output.
    """
    if sys.platform != "win32":
        return 1, "--download-all-windows-wheels is only supported on Windows.\n"
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    pypi = "https://pypi.org/simple"
    chunks: list[str] = []
    any_fail = False
    for name, index_url in _PYTORCH_WINDOWS_WHEEL_VARIANTS:
        if on_variant_start:
            on_variant_start(name)
        sub = dest / name
        sub.mkdir(parents=True, exist_ok=True)
        exe = pip_python(python_exe, role=f"dl-{name}")
        cmd = exe + [
            "-m",
            "pip",
            "download",
            "--upgrade",
            "--index-url",
            index_url,
            "--extra-index-url",
            pypi,
            "-d",
            str(sub),
            "--progress-bar",
            "on",
        ] + _TORCH_PKGS
        if on_line:
            on_line(f"# pip download -> {sub} ({index_url})")
        code, out = _run_pip(cmd, on_line, None, None)
        header = f"# Variant {name}\n# {' '.join(cmd)}\n\n"
        chunks.append(header + out)
        if code != 0:
            any_fail = True
    return (1 if any_fail else 0), "\n\n".join(chunks)


def install_pytorch_then_rest(
    *,
    python_exe: str | None = None,
    force_cuda_if_applicable: bool = True,
    on_line: Callable[[str], None] | None = None,
    on_first_pip_output: Callable[[str], None] | None = None,
    subprocess_ref: PipSubprocessRef | None = None,
) -> tuple[int, str]:
    """Install matching PyTorch, then ``pip install -r requirements.txt``."""
    chunks: list[str] = []
    c1, o1 = install_pytorch_for_hardware(
        python_exe=python_exe,
        upgrade=True,
        force_cuda_if_applicable=force_cuda_if_applicable,
        on_line=on_line,
        on_first_pip_output=on_first_pip_output,
        subprocess_ref=subprocess_ref,
    )
    chunks.append(o1)
    if c1 != 0:
        return c1, "\n\n".join(chunks)
    c2, o2 = install_requirements_runtime(
        python_exe=python_exe,
        on_line=on_line,
        on_first_pip_output=on_first_pip_output,
        subprocess_ref=subprocess_ref,
    )
    chunks.append(o2)
    return c2, "\n\n".join(chunks)


def _cli_live_line(s: str) -> None:
    """Print pip/stream lines immediately (unbuffered) for terminal and log capture."""
    print(s, flush=True)


def _configure_stdout_for_live_logs() -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdout_for_live_logs()
    p = argparse.ArgumentParser(description="Install PyTorch matched to CPU/GPU, optionally the rest of Aquaduct deps.")
    p.add_argument(
        "--with-rest",
        action="store_true",
        help="After PyTorch, run pip install -r requirements.txt",
    )
    p.add_argument(
        "--python",
        dest="pythons",
        action="append",
        metavar="EXE",
        default=None,
        help=(
            "Python executable to use (default: the interpreter running this script). "
            "Pass multiple times to install into several environments, e.g. project venv and a global Python."
        ),
    )
    p.add_argument(
        "--no-force-cuda-switch",
        action="store_true",
        help="Do not uninstall CPU-only torch when NVIDIA GPU is present.",
    )
    p.add_argument(
        "--download-all-windows-wheels",
        metavar="DEST",
        nargs="?",
        const="torch_wheels",
        default=None,
        help=(
            "Windows only: pip download torch torchvision torchaudio wheels into "
            "DEST/cu128, cu124, ... (relative paths resolve under the repo root). "
            "If the flag is given with no path, uses ./torch_wheels. "
            "Does not run --with-rest."
        ),
    )
    p.add_argument(
        "--plain",
        action="store_true",
        help="Disable Rich progress UI; print pip lines only (also set AQUADUCT_PLAIN_CLI=1).",
    )
    args = p.parse_args(argv)

    if args.plain:
        os.environ["AQUADUCT_PLAIN_CLI"] = "1"

    if args.download_all_windows_wheels is not None and args.with_rest:
        p.error("Cannot combine --with-rest with --download-all-windows-wheels")

    if args.download_all_windows_wheels is not None:
        raw = args.download_all_windows_wheels
        dest = Path(raw)
        if not dest.is_absolute():
            dest = repo_root() / dest
        py0 = args.pythons[0] if args.pythons else None
        variant_names = tuple(n for n, _ in _PYTORCH_WINDOWS_WHEEL_VARIANTS)
        try:
            from src.util.cli_pip_display import rich_windows_wheels_session, use_rich_cli
        except ImportError:
            use_rich_cli = lambda: False  # type: ignore[assignment, misc]
            rich_windows_wheels_session = None  # type: ignore[assignment]

        if use_rich_cli() and rich_windows_wheels_session is not None:
            with rich_windows_wheels_session(variant_names) as (on_line, on_variant_start):
                code, out = download_all_windows_torch_wheels(
                    dest,
                    python_exe=py0,
                    on_line=on_line,
                    on_variant_start=on_variant_start,
                )
        else:
            code, out = download_all_windows_torch_wheels(dest, python_exe=py0, on_line=_cli_live_line)
        if code != 0 or not use_rich_cli():
            print(out, flush=True)
        if code == 0:
            print(
                f"\n# Done. Wheels under {dest.resolve()} - use the variant that matches your GPU "
                f"(cu128 ~ Blackwell / RTX 50-series; cu124 ~ most older NVIDIA GPUs), e.g.\n"
                f"#   py -m pip install --no-index --find-links \"{dest.resolve()}\\cu128\" torch torchvision torchaudio\n",
                flush=True,
            )
        return int(code)

    targets: list[str | None] = [None] if args.pythons is None else list(args.pythons)
    force_cuda = not args.no_force_cuda_switch

    try:
        from src.util.cli_pip_display import rich_pip_install_session, use_rich_cli
    except ImportError:
        use_rich_cli = lambda: False  # type: ignore[assignment, misc]
        rich_pip_install_session = None  # type: ignore[assignment]

    last_code = 0
    for i, py_exe in enumerate(targets):
        label = py_exe or sys.executable
        print(f"\n{'=' * 72}", flush=True)
        print(f"# Install target {i + 1}/{len(targets)}: {label}", flush=True)
        print(f"{'=' * 72}\n", flush=True)
        if use_rich_cli() and rich_pip_install_session is not None:
            with rich_pip_install_session(with_requirements_phase=bool(args.with_rest)) as on_line:
                if args.with_rest:
                    code, out = install_pytorch_then_rest(
                        python_exe=py_exe,
                        force_cuda_if_applicable=force_cuda,
                        on_line=on_line,
                    )
                else:
                    code, out = install_pytorch_for_hardware(
                        python_exe=py_exe,
                        upgrade=True,
                        force_cuda_if_applicable=force_cuda,
                        on_line=on_line,
                    )
        else:
            if args.with_rest:
                code, out = install_pytorch_then_rest(
                    python_exe=py_exe,
                    force_cuda_if_applicable=force_cuda,
                    on_line=_cli_live_line,
                )
            else:
                code, out = install_pytorch_for_hardware(
                    python_exe=py_exe,
                    upgrade=True,
                    force_cuda_if_applicable=force_cuda,
                    on_line=_cli_live_line,
                )
        if code != 0 and use_rich_cli():
            print(out, flush=True)
        last_code = int(code)
        if last_code != 0:
            return last_code
    return last_code


if __name__ == "__main__":
    raise SystemExit(main())
