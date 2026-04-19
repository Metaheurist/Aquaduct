from __future__ import annotations

import json
import random
import re
import uuid
import zlib
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from src.core.config import AppSettings, get_paths
from .topics import normalize_video_format


def characters_path() -> Path:
    return get_paths().data_dir / "characters.json"


_MAX_FIELD = 8000
_MAX_NAME = 120

# Public aliases for callers that clip generated text (e.g. brain LLM helpers).
CHARACTER_FIELD_MAX_LEN = _MAX_FIELD
CHARACTER_NAME_MAX_LEN = _MAX_NAME


def _clip(s: str, n: int) -> str:
    t = (s or "").strip()
    return t[:n] if len(t) > n else t


@dataclass
class Character:
    """User-defined character profile for script + visuals + optional TTS override."""

    id: str
    name: str
    identity: str = ""
    visual_style: str = ""
    negatives: str = ""
    #: Relative to application data dir, e.g. ``characters/<id>/portrait.png`` (see :func:`character_portrait_abs_path`).
    reference_image_rel: str = ""
    use_default_voice: bool = True
    pyttsx3_voice_id: str = ""
    kokoro_voice: str = ""
    elevenlabs_voice_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "identity": self.identity,
            "visual_style": self.visual_style,
            "negatives": self.negatives,
            "reference_image_rel": self.reference_image_rel,
            "use_default_voice": self.use_default_voice,
            "pyttsx3_voice_id": self.pyttsx3_voice_id,
            "kokoro_voice": self.kokoro_voice,
            "elevenlabs_voice_id": self.elevenlabs_voice_id,
        }

    @staticmethod
    def from_dict(d: Any) -> Character | None:
        if not isinstance(d, dict):
            return None
        raw_id = str(d.get("id") or "").strip()
        if not raw_id or len(raw_id) < 8 or not re.match(r"^[a-f0-9]{8,64}$", raw_id):
            return None
        name = _clip(str(d.get("name", "")), _MAX_NAME)
        if not name:
            return None
        return Character(
            id=raw_id,
            name=name,
            identity=_clip(str(d.get("identity", "")), _MAX_FIELD),
            visual_style=_clip(str(d.get("visual_style", "")), _MAX_FIELD),
            negatives=_clip(str(d.get("negatives", "")), _MAX_FIELD),
            reference_image_rel=_clip(str(d.get("reference_image_rel", "")), 512),
            use_default_voice=bool(d.get("use_default_voice", True)),
            pyttsx3_voice_id=_clip(str(d.get("pyttsx3_voice_id", "")), 512),
            kokoro_voice=_clip(str(d.get("kokoro_voice", "")), 256),
            elevenlabs_voice_id=_clip(str(d.get("elevenlabs_voice_id", "")), 128),
        )


def load_all() -> list[Character]:
    p = characters_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out: list[Character] = []
    seen: set[str] = set()
    for item in raw:
        c = Character.from_dict(item)
        if c is None or c.id in seen:
            continue
        seen.add(c.id)
        out.append(c)
    return out


def save_all(characters: list[Character]) -> None:
    p = characters_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = [c.to_dict() for c in characters]
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def get_by_id(characters: list[Character], cid: str) -> Character | None:
    c = str(cid or "").strip()
    if not c:
        return None
    for ch in characters:
        if ch.id == c:
            return ch
    return None


def upsert(characters: list[Character], character: Character) -> list[Character]:
    others = [c for c in characters if c.id != character.id]
    others.append(character)
    others.sort(key=lambda x: x.name.lower())
    return others


def delete_by_id(characters: list[Character], cid: str) -> list[Character]:
    c = str(cid or "").strip()
    return [x for x in characters if x.id != c]


def new_character(*, name: str) -> Character:
    return Character(
        id=uuid.uuid4().hex,
        name=_clip(name, _MAX_NAME) or "Unnamed",
        identity="",
        visual_style="",
        negatives="",
        reference_image_rel="",
        use_default_voice=True,
        pyttsx3_voice_id="",
        kokoro_voice="",
        elevenlabs_voice_id="",
    )


def character_portrait_relpath(character_id: str) -> str:
    cid = str(character_id or "").strip()
    if not cid:
        return ""
    return f"characters/{cid}/portrait.png"


def character_portrait_abs_path(character_id: str) -> Path:
    return get_paths().data_dir / character_portrait_relpath(character_id)


def character_reference_image_resolved(ch: Character) -> Path | None:
    """Absolute path to the saved reference portrait if it exists on disk."""
    rel = (ch.reference_image_rel or "").strip()
    if not rel:
        p = character_portrait_abs_path(ch.id)
        return p if p.is_file() else None
    p = get_paths().data_dir / rel.replace("\\", "/").lstrip("/")
    return p if p.is_file() else None


def delete_character_assets(character_id: str) -> None:
    """Best-effort remove on-disk folder for a character (portraits, temps)."""
    import shutil

    cid = str(character_id or "").strip()
    if not cid:
        return
    root = get_paths().data_dir / "characters" / cid
    if root.is_dir():
        try:
            shutil.rmtree(root, ignore_errors=True)
        except Exception:
            pass


def resolve_active_character(settings: AppSettings) -> Character | None:
    cid = str(getattr(settings, "active_character_id", "") or "").strip()
    if not cid:
        return None
    return get_by_id(load_all(), cid)


def _ephemeral_character_for_show(
    *,
    video_format: str,
    topic_tags: list[str] | None,
    headline_seed: str,
) -> Character:
    """In-memory cast when the user has no saved characters — not written to disk."""
    vf = normalize_video_format(video_format)
    seed = f"{headline_seed}|{vf}|{'|'.join(topic_tags or [])}"
    digest = zlib.adler32(seed.encode("utf-8", errors="ignore")) & 0xFFFFFFFF
    rng = random.Random(digest)

    first = rng.choice(
        ["Jordan", "Riley", "Casey", "Morgan", "Quinn", "Avery", "Jamie", "Drew", "Sage", "Remy"]
    )
    last = rng.choice(
        ["Vex", "Noodle", "Kettle", "Flux", "Spindle", "Gribble", "Wobble", "Thunk", "Pocket", "Lint"]
    )
    name = f"{first} {last}"
    tag_hint = ", ".join((topic_tags or [])[:4]) or "general audience"

    if vf == "unhinged":
        identity = (
            f"The show's core cast for this vertical: {name} is the cynical host who commits to the bit; "
            "a recurring off-screen foil (voice-only) interrupts with fake moral authority. "
            f"Topic vibe: {tag_hint}. Invent original jokes — do not reference real shows or celebrities."
        )
        visual = (
            "Flat 2D adult-animation satire, exaggerated expressions, sitcom staging, gross-out or surreal "
            "backgrounds when needed, 9:16 vertical"
        )
    elif vf == "cartoon":
        identity = (
            f"Host character {name}: playful, expressive, slightly chaotic energy for cartoon comedy. "
            f"Topic vibe: {tag_hint}."
        )
        visual = "Bright 2D cartoon, bold outlines, rubber-hose motion, friendly palette, 9:16 vertical"
    elif vf == "explainer":
        identity = (
            f"Host {name}: patient educator — clear, curious, slightly nerdy — guides the viewer. "
            f"Topic vibe: {tag_hint}."
        )
        visual = (
            "Clean infographic-adjacent visuals, diagrams, soft gradients, readable text overlays, 9:16 vertical"
        )
    else:
        identity = (
            f"Host {name}: credible short-form host — fast, skeptical, plain language. "
            f"Topic vibe: {tag_hint}."
        )
        visual = (
            "High-contrast cyberpunk HUD accents, subtle glitch, readable captions, 9:16 vertical"
        )

    negatives = "Slurs, hate, harassment, or real-person cruelty; do not copy real shows or characters."

    return Character(
        id=uuid.uuid4().hex,
        name=name,
        identity=identity,
        visual_style=visual,
        negatives=negatives,
        reference_image_rel="",
        use_default_voice=True,
        pyttsx3_voice_id="",
        kokoro_voice="",
        elevenlabs_voice_id="",
    )


def resolve_character_for_pipeline(
    settings: AppSettings,
    *,
    video_format: str = "news",
    topic_tags: list[str] | None = None,
    headline_seed: str = "",
) -> Character:
    """
    Character for script, visuals, and optional voice overrides.

    Uses the active character when set; otherwise the first saved character (by name);
    otherwise generates a one-off in-memory character for this run (no disk write).
    """
    ch = resolve_active_character(settings)
    if ch is not None:
        return ch
    all_c = load_all()
    if all_c:
        return sorted(all_c, key=lambda x: x.name.lower())[0]
    return _ephemeral_character_for_show(
        video_format=video_format,
        topic_tags=topic_tags,
        headline_seed=headline_seed or "",
    )


def character_context_for_brain(ch: Character) -> str:
    """Block text appended to the LLM system prompt (identity only)."""
    parts = [f"Character name: {ch.name}"]
    if ch.identity.strip():
        parts.append(f"Identity / channel persona (must stay consistent in narration and on-screen cues):\n{ch.identity.strip()}")
    if ch.visual_style.strip():
        parts.append(
            f"Visual direction (prefer imagery and on_screen_text that align with this; segment visual_prompt may elaborate per scene):\n{ch.visual_style.strip()}"
        )
    if character_reference_image_resolved(ch) is not None:
        parts.append(
            "Canonical host reference portrait: a still image of this character was generated and saved for the project. "
            "Treat it as the ground-truth look — keep the same silhouette, palette, and wardrobe vibe as visual_style when describing scenes; "
            "segment visuals should stay consistent with this host (not a different person each cut)."
        )
    if ch.negatives.strip():
        parts.append(f"Boundaries / avoid:\n{ch.negatives.strip()}")
    return "\n\n".join(parts)
