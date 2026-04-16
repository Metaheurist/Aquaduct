"""
Human-readable labels for per-task progress (each task reports its own 0–100%).
"""

from __future__ import annotations

# Stable task ids emitted by workers (preview, storyboard, downloads, batch run).
TASK_LABELS: dict[str, str] = {
    "headlines": "Headlines",
    "personality": "Personality",
    "script_llm_load": "Script model (load)",
    "script_llm_gen": "Script model (write)",
    "preview": "Preview wrap-up",
    "storyboard_build": "Storyboard layout",
    "storyboard_images": "Preview images",
    "storyboard_grid": "Storyboard grid",
    "download": "Download",
    "pipeline_video": "Pipeline video",
    "storyboard": "Storyboard",  # final ready
}


def label_for(task_id: str) -> str:
    return TASK_LABELS.get(task_id, task_id.replace("_", " ").title())


def format_status_line(task_id: str, pct: int, message: str) -> str:
    return f"{label_for(task_id)}: {message} — {pct}%"

