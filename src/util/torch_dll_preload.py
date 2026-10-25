"""Load PyTorch's core DLL before Qt on Windows.

Once PyQt6 has loaded its own runtime DLLs, ``import torch`` (2.x CUDA wheels) fails with
``WinError 1114`` while initialising ``c10.dll``. Loading ``c10.dll`` first takes a few
milliseconds and lets the full ``import torch`` succeed later, without paying torch's
import cost at startup.
"""

from __future__ import annotations

import os
import sys


def preload_torch_dlls() -> bool:
    """Best effort; returns True when ``c10.dll`` was loaded. No-op off Windows."""
    if os.name != "nt" or "torch" in sys.modules:
        return False
    try:
        import ctypes
        import importlib.util

        spec = importlib.util.find_spec("torch")
        if spec is None or not spec.origin:
            return False
        lib_dir = os.path.join(os.path.dirname(spec.origin), "lib")
        c10 = os.path.join(lib_dir, "c10.dll")
        if not os.path.isfile(c10):
            return False
        os.add_dll_directory(lib_dir)
        ctypes.WinDLL(c10)
        return True
    except Exception:
        return False
