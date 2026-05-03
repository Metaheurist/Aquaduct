"""Video playground prompt length hints — aligned with ``src/render/clips`` caps and cloud API truncation."""

from __future__ import annotations

from typing import Literal

from src.render.clips import _img2vid_accepts_text_prompt, is_image_to_video_motion_model

PlaygroundMotionUIKind = Literal[
    "api_t2v",
    "local_t2v",
    "local_img2vid_image_only",
    "local_img2vid_with_text",
]


def _norm_repo_id(model_id: str) -> str:
    return (model_id or "").strip().lower()


def video_playground_motion_ui_kind(
    *,
    mode: Literal["local", "api"],
    video_repo_id: str = "",
) -> PlaygroundMotionUIKind:
    """How the video playground should present inputs for the current target."""
    if mode == "api":
        return "api_t2v"
    repo = (video_repo_id or "").strip()
    if not is_image_to_video_motion_model(repo):
        return "local_t2v"
    if not _img2vid_accepts_text_prompt(repo):
        return "local_img2vid_image_only"
    return "local_img2vid_with_text"


def video_playground_prompt_char_limit(
    *,
    mode: Literal["local", "api"],
    video_repo_id: str = "",
    api_provider: str = "",
    api_model: str = "",
    motion_ui_kind: PlaygroundMotionUIKind | None = None,
) -> tuple[int, str]:
    """
    Return ``(max_chars, one_line_rationale)`` for the video playground prompt box.

    Local limits follow word / CLIP heuristics in :func:`src.render.clips._strip_negative_and_cap_for_clip`.
    API limits match client-side truncation where implemented (Kling / Magic Hour).
    """
    muk = motion_ui_kind or video_playground_motion_ui_kind(mode=mode, video_repo_id=video_repo_id)
    if muk == "local_img2vid_image_only":
        return (
            0,
            "This checkpoint animates the still only — there is no text-conditioning path in the pipeline.",
        )

    if mode == "api":
        p = (api_provider or "").strip().lower()
        if p == "kling":
            return (
                2000,
                "Kling text-to-video uses at most 2000 characters (same as the API request).",
            )
        if p == "magic_hour":
            return (
                2000,
                "Magic Hour style.prompt is truncated to 2000 characters in the API client.",
            )
        if p == "replicate":
            return (
                2500,
                "Replicate models vary; 2500 characters is a safe upper bound for most video versions.",
            )
        return (
            2000,
            "Cloud video: conservative 2000-character cap until a specific provider is selected.",
        )

    low = _norm_repo_id(video_repo_id)
    if not low:
        return (
            320,
            "Pick a video model on the Model tab for a tighter limit; default assumes CLIP-size text (~77 tokens, ~320 characters).",
        )
    if "cogvideox" in low:
        return (
            1800,
            "CogVideoX allows long prompts in the pipeline (~200 words); ~1800 characters keeps paste-sized prompts safe.",
        )
    if "ltx-video" in low or "lightricks/ltx" in low:
        return (
            1200,
            "LTX uses a long context encoder; the pipeline caps ~120 words — ~1200 characters as a practical UI limit.",
        )
    if "mochi" in low or "wan-ai" in low or "wan2" in low:
        return (
            2000,
            "Mochi / Wan use long prompts in the pipeline (~200 words); ~2000 characters matches that headroom.",
        )
    if "zeroscope" in low or "text-to-video-ms" in low or "modelscope" in low:
        return (
            320,
            "ZeroScope / ModelScope use a CLIP text encoder (~77 tokens); the pipeline hard-limits near 320 characters.",
        )
    if "hunyuanvideo" in low:
        return (
            320,
            "Hunyuan applies a CLIP-style budget after word trimming; ~320 characters matches the pipeline cap.",
        )
    return (
        320,
        "This local motion stack likely uses a CLIP-sized text encoder (~77 tokens); ~320 characters matches the pipeline safety cap.",
    )
