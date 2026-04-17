#!/usr/bin/env python3
"""CLI wrapper: installs PyTorch matched to hardware, optionally all other deps."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.torch_install import main

if __name__ == "__main__":
    raise SystemExit(main())
