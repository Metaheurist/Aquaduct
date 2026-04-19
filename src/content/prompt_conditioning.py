from __future__ import annotations

import re
from typing import Literal


SceneType = Literal["broll", "infographic", "portrait", "product_shot", "timeline", "map"]


def assign_scene_types(prompts: list[str]) -> list[SceneType]:
    """
    Assign a scene type per prompt, enforcing variety (no repeats back-to-back).
    """
    out: list[SceneType] = []
    last: SceneType | None = None
    cycle: list[SceneType] = ["product_shot", "infographic", "broll", "timeline", "portrait", "map"]
    ci = 0

    for p in prompts or []:
        pl = (p or "").lower()
        guess: SceneType | None = None
        if any(k in pl for k in ("timeline", "before/after", "roadmap", "over time")):
            guess = "timeline"
        elif any(k in pl for k in ("map", "world", "country", "region")):
            guess = "map"
        elif any(k in pl for k in ("infographic", "chart", "graph", "stats", "numbers")):
            guess = "infographic"
        elif any(k in pl for k in ("portrait", "person", "founder", "creator", "developer")):
            guess = "portrait"
        elif any(k in pl for k in ("dashboard", "ui", "app", "product", "interface")):
            guess = "product_shot"
        else:
            guess = "broll"

        if last is not None and guess == last:
            # rotate to next in cycle
            for _ in range(len(cycle)):
                cand = cycle[ci % len(cycle)]
                ci += 1
                if cand != last:
                    guess = cand
                    break

        out.append(guess)
        last = guess
    return out


def default_negative_prompt() -> str:
    return (
        "low quality, blurry, jpeg artifacts, watermark, logo, "
        "text, letters, words, typography, subtitles, captions burned into image, "
        "speech bubbles with text, newspaper text, signage with readable text, UI text overlay, "
        "readable writing, title card, lower third text, "
        "deformed, extra limbs, bad anatomy, low contrast, washed out, oversaturated, "
        "nsfw"
    )


def camera_cues(scene_type: SceneType, *, idx: int) -> str:
    # small rotating set; idx is beat index
    cues = {
        "product_shot": ["close-up UI screenshot, crisp", "over-the-shoulder screen view", "angled UI panel, cinematic"],
        "infographic": ["clean infographic panel", "minimal chart overlay", "numbers and icons layout"],
        "broll": ["cinematic b-roll, shallow depth of field", "moody lighting, dynamic composition", "slow shutter feel, crisp"],
        "timeline": ["timeline overlay, clear steps", "roadmap panel, icons", "before/after split layout"],
        "portrait": ["portrait lighting, rim light", "studio portrait, cyberpunk", "close-up face, cinematic"],
        "map": ["map overlay, subtle grid", "world map HUD", "location pins, neon"],
    }
    arr = cues.get(scene_type, ["cinematic framing"])
    return arr[int(idx) % len(arr)]


def condition_prompt(
    prompt: str,
    *,
    scene_type: SceneType,
    idx: int,
    negatives: str | None = None,
) -> str:
    p = (prompt or "").strip()
    if not p:
        p = "high-contrast cyberpunk UI, neon, sharp, cinematic, 9:16 composition"

    cue = camera_cues(scene_type, idx=idx)
    neg = (negatives or default_negative_prompt()).strip()

    # Avoid duplicating if already present
    if cue.lower() not in p.lower():
        p = f"{p}, {cue}"
    if "9:16" not in p and "vertical" not in p.lower():
        p = f"{p}, vertical 9:16"

    # Keep negatives in a stable suffix for downstream models that accept it textually.
    if "NEGATIVE:" not in p:
        p = f"{p}\nNEGATIVE: {neg}"
    return p

