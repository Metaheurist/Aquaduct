from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class FrameQuality:
    variance: float
    contrast: float
    laplacian_var: float


def _laplacian_var(gray: np.ndarray) -> float:
    # Simple 2D Laplacian approximation without OpenCV.
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    # pad
    g = np.pad(gray.astype(np.float32), 1, mode="edge")
    out = (
        k[0, 0] * g[:-2, :-2]
        + k[0, 1] * g[:-2, 1:-1]
        + k[0, 2] * g[:-2, 2:]
        + k[1, 0] * g[1:-1, :-2]
        + k[1, 1] * g[1:-1, 1:-1]
        + k[1, 2] * g[1:-1, 2:]
        + k[2, 0] * g[2:, :-2]
        + k[2, 1] * g[2:, 1:-1]
        + k[2, 2] * g[2:, 2:]
    )
    return float(out.var())


def score_frame(path: Path) -> FrameQuality:
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    gray = (0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]).astype(np.float32)
    variance = float(gray.var())
    contrast = float(np.percentile(gray, 95) - np.percentile(gray, 5))
    lap = _laplacian_var((gray * 255.0).astype(np.uint8))
    return FrameQuality(variance=variance, contrast=contrast, laplacian_var=lap)


def is_reject(q: FrameQuality, *, min_variance: float = 0.0025, min_contrast: float = 0.15, min_laplacian: float = 30.0) -> bool:
    # near-blank / monochrome
    if q.variance < min_variance:
        return True
    if q.contrast < min_contrast:
        return True
    if q.laplacian_var < min_laplacian:
        return True
    return False

