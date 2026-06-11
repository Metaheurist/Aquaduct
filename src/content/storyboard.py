from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .brain import VideoPackage
from .characters_store import Character, character_reference_image_resolved, subject_token_phrase
from debug import dprint
from .prompt_conditioning import assign_scene_types, condition_prompt, default_negative_prompt, scene_type_from_prompt_text


SceneRole = Literal["broll", "infographic", "product_shot", "portrait", "timeline", "map"]
ShotType = Literal[
    "wide",
    "medium",
    "close",
    "extreme_close",
    "ots",
    "pov",
    "dutch",
    "low_angle",
    "high_angle",
]
OverlayType = Literal["none", "headline", "keywords"]
MotionType = Literal["still", "kenburns"]
SceneStatus = Literal["pending", "approved", "regenerated"]


@dataclass(frozen=True)
class StoryboardScene:
    idx: int
    prompt: str
    seed: int
    negative_prompt: str = ""
    scene_role: SceneRole = "broll"
    shot_type: ShotType = "medium"
    overlay: OverlayType = "none"
    motion: MotionType = "still"
    narration: str = ""
    on_screen_text: str = ""
    image_path: str = ""
    preview_image_path: str = ""
    status: SceneStatus = "pending"
    lock_seed: bool = False


@dataclass(frozen=True)
class Storyboard:
    title: str
    scenes: list[StoryboardScene]


def _guess_role(prompt: str) -> SceneRole:
    return scene_type_from_prompt_text(prompt)  # type: ignore[return-value]


def _rotate_no_repeat(seq: list[SceneRole]) -> list[SceneRole]:
    out: list[SceneRole] = []
    last: SceneRole | None = None
    for r in seq:
        if last is not None and r == last:
            # pick a different role (simple rotation preference)
            for cand in ("product_shot", "infographic", "broll", "timeline", "portrait", "map"):
                if cand != last:
                    r = cand  # type: ignore[assignment]
                    break
        out.append(r)
        last = r
    return out


def _shot_cycle(i: int, video_format: str | None = None) -> ShotType:
    vf = (video_format or "news").strip().lower()
    if vf == "creepypasta":
        seq: tuple[str, ...] = (
            "wide",
            "medium",
            "close",
            "dutch",
            "pov",
            "low_angle",
            "extreme_close",
            "high_angle",
        )
    elif vf in ("cartoon", "unhinged"):
        seq = ("medium", "close", "wide", "low_angle", "dutch", "extreme_close", "pov")
    elif vf == "health_advice":
        seq = ("medium", "wide", "close", "ots", "medium", "wide", "close")
    elif vf == "nsfw":
        seq = ("medium", "wide", "close", "medium", "low_angle", "close")
    else:
        seq = ("wide", "medium", "close", "ots", "medium", "low_angle", "close")
    return seq[int(i) % len(seq)]  # type: ignore[return-value]


def _merge_narration_into_weak_prompt(narration: str, visual: str, *, min_words: int = 10) -> str:
    """If the LLM returned a vague visual line, anchor diffusion with a short clause from the spoken beat."""
    v = (visual or "").strip()
    if len(v.split()) >= min_words:
        return v
    words = [w for w in (narration or "").replace("\n", " ").split() if w]
    clip = " ".join(words[:22])
    if not clip:
        return v
    if not v:
        return f"illustration of: {clip}"
    return f"{v}; scene shows: {clip}"


def _overlay_for(scene_text: str, *, idx: int, overlay_budget: int) -> OverlayType:
    if overlay_budget <= 0:
        return "none"
    t = (scene_text or "").lower()
    if any(ch.isdigit() for ch in t) and (idx % 2 == 0):
        return "keywords"
    return "headline" if (idx % 3 == 0) else "none"


def storyboard_from_prebuilt(
    prompts: list[str],
    seeds: list[int],
    *,
    title: str = "Storyboard",
    negative_prompt: str = "",
    video_format: str | None = None,
) -> Storyboard:
    """Build a minimal storyboard from finalized prompts/seeds (skip LLM-derived scene assembly)."""
    scenes: list[StoryboardScene] = []
    for i, (prompt, seed) in enumerate(zip(prompts, seeds), start=1):
        role = _guess_role(prompt)
        scenes.append(
            StoryboardScene(
                idx=i,
                prompt=str(prompt).strip(),
                seed=int(seed),
                negative_prompt=negative_prompt,
                scene_role=role,
                shot_type=_shot_cycle(i - 1, video_format),
                overlay=_overlay_for(prompt, idx=i, overlay_budget=2),
                motion="kenburns"
                if _shot_cycle(i - 1, video_format) in ("wide", "medium", "low_angle", "high_angle", "ots")
                else "still",
            )
        )
    return Storyboard(title=title or "Storyboard", scenes=scenes)


def build_storyboard(
    pkg: VideoPackage,
    *,
    seed_base: int | None,
    branding=None,
    max_scenes: int = 10,
    character: Character | None = None,
    video_format: str | None = None,
) -> Storyboard:
    """
    Convert VideoPackage beats into storyboarded scenes with roles/shot types/overlays and deterministic seeds.
    """
    dprint("storyboard", "build_storyboard", f"title={pkg.title[:80]!r}", f"max_scenes={max_scenes}")
    segs = list(pkg.segments or [])[: max(1, int(max_scenes))]
    raw_prompts = [_merge_narration_into_weak_prompt(s.narration, s.visual_prompt) for s in segs]
    if character is not None:
        vs = (character.visual_style or "").strip()
        st = subject_token_phrase(character)
        if vs or st:
            name_lower = (character.name or "").strip().lower()
            if name_lower.startswith("cast:"):
                merged_vs = vs if vs else st
            else:
                merged_vs = f"{st}, {vs}" if st and vs else (st or vs)
            prompts = [f"{merged_vs}, {p}" if (p or "").strip() else merged_vs for p in raw_prompts]
        else:
            prompts = list(raw_prompts)
    else:
        prompts = list(raw_prompts)
    if (
        character is not None
        and prompts
        and character_reference_image_resolved(character) is not None
    ):
        prompts[0] = (
            "Host establishing shot — keep the same character design as the saved reference portrait; "
            + prompts[0]
        )
    roles = _rotate_no_repeat([_guess_role(p) for p in prompts])
    # Apply scene-type prompt conditioning (includes negatives suffix)
    try:
        scene_types = assign_scene_types(prompts)
        neg = default_negative_prompt()
        if character is not None and (character.negatives or "").strip():
            extra = character.negatives.strip()
            neg = f"{neg}, {extra}" if neg else extra
            if len(neg) > 3000:
                neg = neg[:3000]
        prompts = [
            condition_prompt(
                p,
                scene_type=scene_types[i],
                idx=i,
                negatives=neg,
                video_format=video_format,
                shot_type=_shot_cycle(i, video_format),
            )
            for i, p in enumerate(prompts)
        ]
    except Exception:
        pass

    overlay_cap = max(1, int(round(0.40 * len(segs)))) if segs else 0
    overlays_left = overlay_cap

    scenes: list[StoryboardScene] = []
    for i, s in enumerate(segs, start=1):
        seed = int(seed_base) + (i * 9973) if seed_base is not None else (abs(hash((pkg.title, i))) % 2_000_000_000)
        shot = _shot_cycle(i - 1, video_format)
        overlay = _overlay_for((s.on_screen_text or "") + " " + s.narration, idx=i - 1, overlay_budget=overlays_left)
        if overlay != "none":
            overlays_left -= 1
        motion: MotionType = "kenburns" if shot in ("wide", "medium", "low_angle", "high_angle", "ots") else "still"

        neg_prompt = ""
        try:
            # If our condition_prompt already injected a NEGATIVE: line, split it out for manifest clarity.
            pp = prompts[i - 1]
            if "\nNEGATIVE:" in pp:
                base, neg_line = pp.split("\nNEGATIVE:", 1)
                prompts[i - 1] = base.strip()
                neg_prompt = neg_line.strip()
        except Exception:
            neg_prompt = ""

        scenes.append(
            StoryboardScene(
                idx=i,
                prompt=str(prompts[i - 1]),
                negative_prompt=neg_prompt,
                seed=seed,
                scene_role=roles[i - 1],
                shot_type=shot,
                overlay=overlay,
                motion=motion,
                narration=str(s.narration or ""),
                on_screen_text=str(s.on_screen_text or ""),
            )
        )

    return Storyboard(title=pkg.title, scenes=scenes)


def write_manifest(path: Path, *, storyboard: Storyboard, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "title": storyboard.title,
        "settings": settings,
        "scenes": [asdict(s) for s in storyboard.scenes],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def render_preview_grid(*, scene_paths: list[Path], out_grid: Path, cols: int = 4, thumb: int = 256) -> Path:
    """
    Build a simple preview grid PNG from scene images.
    """
    from PIL import Image, ImageDraw, ImageFont

    imgs = [p for p in scene_paths if p.exists()]
    if not imgs:
        raise ValueError("No preview images to grid.")
    cols = max(1, int(cols))
    rows = (len(imgs) + cols - 1) // cols
    pad = 14
    w = cols * thumb + (cols + 1) * pad
    h = rows * thumb + (rows + 1) * pad
    canvas = Image.new("RGB", (w, h), (15, 15, 18))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()

    for i, p in enumerate(imgs, start=1):
        im = Image.open(p).convert("RGB")
        im = im.resize((thumb, thumb))
        r = (i - 1) // cols
        c = (i - 1) % cols
        x = pad + c * (thumb + pad)
        y = pad + r * (thumb + pad)
        canvas.paste(im, (x, y))
        draw.text((x + 6, y + 6), f"{i}", fill=(255, 255, 255), font=font)

    out_grid.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_grid)
    return out_grid


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

