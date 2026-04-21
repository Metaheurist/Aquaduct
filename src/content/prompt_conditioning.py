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


def camera_cues(
    scene_type: SceneType,
    *,
    idx: int,
    video_format: str | None = None,
) -> str:
    """Small rotating set; idx is beat index. Comedy formats avoid cyberpunk/UI defaults that fight meme topics."""
    vf = (video_format or "").strip().lower()
    if vf == "creepypasta":
        cues = {
            "product_shot": [
                "cursed object on a table, single candle, deep shadows, film grain",
                "close-up of an old phone or tape recorder, scratched metal, low key light",
                "talisman or locket hero shot, shallow depth of field, fog",
            ],
            "infographic": [
                "fake missing poster on a wall, yellowed paper, unsettling but no readable long text",
                "timeline of wrong dates scratched into wall, chalk smears, horror mood",
                "polaroid collage pinned with red string, conspiracy board vibe, dim bulb",
            ],
            "broll": [
                "foggy forest path at blue hour, silhouetted trees, handheld drift",
                "empty stairwell, one buzzing light, liminal dread, vertical framing",
                "rain-streaked window at night, distant figure blur, no gore",
            ],
            "timeline": [
                "old calendar pages peeling, dates circled wrong, shadow across desk",
                "night-to-dawn timelapse feel, moon arc, creeping fog",
                "sequence of doors getting closer, wrong perspective, uneasy spacing",
            ],
            "portrait": [
                "half-lit face in darkness, fearful eyes, subtle tears, cinematic horror portrait",
                "silhouette portrait backlit by doorway light, rim fog, 9:16",
                "vintage portrait photo texture, cracked frame, uncanny smile implied not gory",
            ],
            "map": [
                "hand-drawn map with X marks, coffee stains, low lamp light",
                "subway map wrong-line glitch, liminal transit horror, desaturated",
                "small town map with forest edge highlighted, ominous red pencil",
            ],
        }
    elif vf in ("cartoon", "unhinged"):
        cues = {
            "product_shot": [
                "big prop or object hero shot, sticker-like clarity, chunky outlines",
                "close-up of a silly gadget or meme object, flat colors, readable silhouette",
                "toy-like product gag, exaggerated scale, comic framing",
            ],
            "infographic": [
                "crude meme diagram, chunky arrows, loud flat color blocks",
                "MS-Paint energy chart joke, hand-drawn icons, high contrast",
                "fake infographic satire, silly labels, crowded comic layout",
            ],
            "broll": [
                "surreal meme tableau, crowded frame, thick ink outlines, garish colors",
                "shitpost cartoon staging, wrong perspective on purpose, expressive poses",
                "Vine-panel energy, one absurd focal gag, maximalist background clutter",
            ],
            "timeline": [
                "chaotic meme storyboard strip, uneven panels, doodle arrows",
                "before/after joke layout, exaggerated reaction faces",
                "ridiculous roadmap parody, silly milestone icons",
            ],
            "portrait": [
                "big expressive toon face, thick black outlines, wild hair, meme reaction energy",
                "character bust with exaggerated features, cel-shaded, NOT neon cyberpunk portrait",
                "close-up mugshot gag, sticker portrait, high-contrast fill light",
            ],
            "map": [
                "silly exaggerated map doodle, meme geography, chunky borders",
                "fake travel meme map, ridiculous labels, bright flat colors",
                "cartoon globe gag, distorted continents for the joke",
            ],
        }
    else:
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
    video_format: str | None = None,
) -> str:
    p = (prompt or "").strip()
    vf = (video_format or "").strip().lower()
    if not p:
        if vf == "creepypasta":
            p = (
                "atmospheric horror still, liminal interior or foggy exterior, single focal unease, "
                "film grain, low key lighting, vertical 9:16, no readable text, no gore"
            )
        elif vf in ("cartoon", "unhinged"):
            p = (
                "figurative surreal meme cartoon, thick black outlines, flat garish colors, "
                "one clear joke focal subject, vertical 9:16, not abstract neon machinery"
            )
        else:
            # Neutral default — avoid forcing cyberpunk/UI when the script is news or unrelated topics.
            p = "single clear focal subject, readable silhouette, cinematic lighting, detailed, vertical 9:16 composition"

    cue = camera_cues(scene_type, idx=idx, video_format=video_format)
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

