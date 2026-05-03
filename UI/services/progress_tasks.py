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
    "pipeline_run": "Pipeline",
    "pipeline_video": "Pipeline video",
    "storyboard": "Storyboard",  # final ready
}


def label_for(task_id: str) -> str:
    return TASK_LABELS.get(task_id, task_id.replace("_", " ").title())


# Show both overall (full run) and step (current sub-task) in the status column.
_DUAL_PROGRESS_TASK_IDS = frozenset({"pipeline_run", "pipeline_video", "download"})


def format_status_line(task_id: str, overall_pct: int, task_pct: int, message: str) -> str:
    """
    ``overall_pct`` is 0–100 for the full job (pipeline run, batch, or multi-model download).
    ``task_pct`` is 0–100 within the current step, or -1 when not tracked (shows overall only).
    """
    label = label_for(task_id)
    o = max(0, min(100, int(overall_pct)))
    if task_pct < 0 or task_id not in _DUAL_PROGRESS_TASK_IDS:
        return f"{label}: {message} - {o}%"
    t = max(0, min(100, int(task_pct)))
    return f"{label}: {message} - total {o}% · step {t}%"

