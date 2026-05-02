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
    #: Free-form TTS *instruction* (e.g. for MOSS-VoiceGenerator: describe timbre, age, energy).
    voice_instruction: str = ""
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
            "voice_instruction": self.voice_instruction,
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
            voice_instruction=_clip(str(d.get("voice_instruction", "")), _MAX_FIELD),
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
        voice_instruction="",
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
        foil_first = rng.choice(["Blake", "Taylor", "Harper", "Rowan", "Reese", "Parker", "Sam", "Alex"])
        foil_last = rng.choice(["Buzzer", "Muffin", "Staple", "Sprocket", "Gizmo", "Biscuit", "Pebble", "Widget"])
        foil = f"{foil_first} {foil_last}"
        identity = (
            "Cast for this vertical (at least 2 characters):\n"
            f"- {name}: cynical host who commits to the bit\n"
            f"- {foil}: recurring foil who interrupts with fake moral authority\n\n"
            f"Topic vibe: {tag_hint}. Invent original jokes — do not reference real shows or celebrities."
        )
        visual = (
            "Flat 2D adult-animation satire, exaggerated expressions, sitcom staging, gross-out or surreal "
            "backgrounds when needed, 9:16 vertical"
        )
    elif vf == "cartoon":
        side_first = rng.choice(["Milo", "Luna", "Nova", "Pip", "Zoe", "Kai", "Nico", "Sunny", "Scout", "Bean"])
        side_last = rng.choice(["Spark", "Pogo", "Waffle", "Tinker", "Doodle", "Bop", "Marble", "Popcorn", "Chirp", "Twig"])
        side = f"{side_first} {side_last}"
        identity = (
            "Cast for this vertical (at least 2 characters):\n"
            f"- {name}: playful, expressive, slightly chaotic energy\n"
            f"- {side}: the straight-man friend who reacts and escalates the joke\n\n"
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
    elif vf == "health_advice":
        role = rng.choice(["doctor", "nurse"])
        identity = (
            f"{role.title()} {name}: warm, credible medical educator for short-form wellness video — plain language, "
            f"no fear-mongering; encourages viewers to seek personal care when needed. Topic vibe: {tag_hint}."
        )
        visual = (
            "Soft clinical teaching look: white coat or scrubs (generic), exam-room or health-education set, "
            "diagrams and stylized anatomy charts, calm lighting, 9:16 vertical — no photoreal gore or identifiable patients"
        )
    elif vf == "creepypasta":
        identity = (
            f"Narrator {name}: calm first-person storyteller — measured, intimate, like a late-night campfire voice. "
            f"Topic vibe: {tag_hint}. Stay in fiction; do not claim real crimes or real people."
        )
        visual = (
            "Cinematic low-key horror stills: fog, silhouettes, liminal hallways, moonlight, grain, implied dread — "
            "9:16 vertical, no splatter or photoreal injury"
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
        voice_instruction="",
        elevenlabs_voice_id="",
    )


def fallback_cast_for_show(*, video_format: str, topic_tags: list[str] | None, headline_seed: str) -> list[dict[str, Any]]:
    """
    Deterministic heuristic cast when LLM cast generation fails.
    Returns a structured list suitable for saving under assets/generated_cast.json.
    """
    vf = normalize_video_format(video_format)
    seed = f"{headline_seed}|{vf}|{'|'.join(topic_tags or [])}"
    digest = zlib.adler32(seed.encode("utf-8", errors="ignore")) & 0xFFFFFFFF
    rng = random.Random(digest)

    def _nm() -> str:
        first = rng.choice(["Jordan", "Riley", "Casey", "Morgan", "Quinn", "Avery", "Jamie", "Drew", "Sage", "Remy"])
        last = rng.choice(["Vex", "Noodle", "Kettle", "Flux", "Spindle", "Gribble", "Wobble", "Thunk", "Pocket", "Lint"])
        return f"{first} {last}"

    tag_hint = ", ".join((topic_tags or [])[:4]) or "general audience"
    neg = "Slurs, hate, harassment, or real-person cruelty; do not copy real shows or characters."
    if vf in ("news", "explainer"):
        host = _nm()
        return [
            {
                "name": host,
                "role": "Narrator/host",
                "identity": f"Host {host}: clear, credible, plain language. Topic vibe: {tag_hint}.",
                "visual_style": (
                    "Clean modern vertical studio look, readable overlays, 9:16"
                    if vf == "news"
                    else "Clean infographic-adjacent visuals, diagrams, readable labels, 9:16"
                ),
                "negatives": neg,
                "voice_instruction": (
                    "Late-20s/30s host, neutral accent, clear and steady mid-pace delivery, slight curiosity"
                ),
            }
        ]

    if vf == "health_advice":
        host = _nm()
        role = rng.choice(["Doctor", "Nurse"])
        return [
            {
                "name": host,
                "role": f"{role} (educator)",
                "identity": (
                    f"{role} {host}: wellness educator — calm, evidence-leaning, never diagnoses the viewer; "
                    f"topic vibe: {tag_hint}."
                ),
                "visual_style": (
                    "Medical education vertical: soft clinic light, diagrams, stylized charts, 9:16 — no gore, no real patients"
                ),
                "negatives": neg,
                "voice_instruction": (
                    "Warm clinical educator, mid-pace delivery, reassuring but factual, no fear-mongering"
                ),
            }
        ]

    if vf == "creepypasta":
        narrator = _nm()
        return [
            {
                "name": narrator,
                "role": "First-person narrator",
                "identity": (
                    f"{narrator}: calm, intimate first-person storyteller — measured campfire delivery; "
                    f"topic vibe: {tag_hint}. Stay in fiction; do not claim real crimes or real people."
                ),
                "visual_style": (
                    "Cinematic low-key horror stills — fog, silhouettes, liminal hallways, moonlight, grain, "
                    "implied dread; 9:16 vertical, no splatter"
                ),
                "negatives": neg,
                "voice_instruction": (
                    "Late-night narrator, hushed, slow campfire pace, occasional pause for tension, no shouting"
                ),
            }
        ]

    a = _nm()
    b = _nm()
    return [
        {
            "name": a,
            "role": "Lead / instigator",
            "identity": f"{a}: commits to the bit, pushes the premise. Topic vibe: {tag_hint}.",
            "visual_style": "Bright 2D cartoon, bold outlines, expressive acting, 9:16 vertical"
            if vf == "cartoon"
            else "Flat 2D adult-animation satire, exaggerated expressions, 9:16 vertical",
            "negatives": neg,
            "voice_instruction": (
                "Energetic, playful, slightly unhinged, fast pace, leans into punchlines"
            ),
        },
        {
            "name": b,
            "role": "Foil / straight-man",
            "identity": f"{b}: reacts, questions, escalates the joke without narrating neutrally.",
            "visual_style": "Bright 2D cartoon, bold outlines, expressive acting, 9:16 vertical"
            if vf == "cartoon"
            else "Flat 2D adult-animation satire, exaggerated expressions, 9:16 vertical",
            "negatives": neg,
            "voice_instruction": (
                "Deadpan, flat affect, a beat slower than the lead, occasional sigh"
            ),
        },
    ]


def resolve_character_for_pipeline(
    settings: AppSettings,
    *,
    video_format: str = "news",
    topic_tags: list[str] | None = None,
    headline_seed: str = "",
) -> Character:
    """
    Character for script, visuals, and optional voice overrides.

    Uses the active character when set; otherwise generates a one-off in-memory character for this run
    (no disk write). Saved characters are only used when explicitly selected.
    """
    ch = resolve_active_character(settings)
    if ch is not None:
        return ch
    return _ephemeral_character_for_show(
        video_format=video_format,
        topic_tags=topic_tags,
        headline_seed=headline_seed or "",
    )


def character_selected_in_settings(settings: AppSettings) -> bool:
    """True when the user explicitly picked a character (active_character_id non-empty)."""
    return bool(str(getattr(settings, "active_character_id", "") or "").strip())


def cast_to_ephemeral_character(*, cast: list[dict[str, Any]], video_format: str) -> Character:
    """
    Convert a generated cast list into a single Character profile that can be injected into the brain prompt.
    This keeps the rest of the pipeline compatible (Character is currently a single object).
    """
    vf = normalize_video_format(video_format)
    # Ensure at least one item exists.
    safe = [c for c in cast if isinstance(c, dict) and str(c.get("name") or "").strip()]
    if not safe:
        return _ephemeral_character_for_show(video_format=vf, topic_tags=None, headline_seed="")

    if vf in ("news", "explainer", "creepypasta", "health_advice"):
        c0 = safe[0]
        name = str(c0.get("name") or "Narrator").strip()[:_MAX_NAME]
        identity = str(c0.get("identity") or "").strip()
        if not identity:
            identity = "Narrator/host: clear, credible, plain language; avoids speculation; hedges uncertainty."
        visual = str(c0.get("visual_style") or "").strip()
        negatives = str(c0.get("negatives") or "").strip()
        voice_instruction = str(c0.get("voice_instruction") or "").strip()
        return Character(
            id=uuid.uuid4().hex,
            name=name or "Narrator",
            identity=_clip(identity, _MAX_FIELD),
            visual_style=_clip(visual, _MAX_FIELD),
            negatives=_clip(negatives, _MAX_FIELD),
            reference_image_rel="",
            use_default_voice=True,
            pyttsx3_voice_id="",
            kokoro_voice="",
            voice_instruction=_clip(voice_instruction, _MAX_FIELD),
            elevenlabs_voice_id="",
        )

    # Comedy modes: embed multiple characters as a cast block.
    names = [str(c.get("name") or "").strip() for c in safe][:4]
    name_line = " & ".join([n for n in names[:2] if n]) or (names[0] if names else "Cast")
    disp = _clip(f"Cast: {name_line}", _MAX_NAME)

    cast_lines: list[str] = []
    visual_bits: list[str] = []
    neg_bits: list[str] = []
    voice_lines: list[str] = []
    for c in safe[:4]:
        nm = str(c.get("name") or "").strip()
        role = str(c.get("role") or "").strip()
        ident = str(c.get("identity") or "").strip()
        vis = str(c.get("visual_style") or "").strip()
        neg = str(c.get("negatives") or "").strip()
        vinst = str(c.get("voice_instruction") or "").strip()
        if nm:
            head = f"- {nm}" + (f" ({role})" if role else "")
            body = f"{head}\n  {ident}" if ident else head
            cast_lines.append(body)
        if vis:
            visual_bits.append(vis)
        if neg:
            neg_bits.append(neg)
        if nm and vinst:
            voice_lines.append(f"- {nm}: {vinst}")

    identity_block = (
        "Cast (mandatory):\n"
        + "\n".join(cast_lines)
        + "\n\nNarration must be in-character dialogue between the cast (or first-person lines), not a neutral announcer.\n"
    )
    visual_style = " | ".join([v for v in visual_bits if v])[:_MAX_FIELD]
    negatives = ", ".join([n for n in neg_bits if n])[:_MAX_FIELD]
    if not negatives:
        negatives = "Slurs, hate, harassment, real-person cruelty; do not copy real shows or characters."

    voice_instruction = (
        ("Cast voice directions (per character):\n" + "\n".join(voice_lines)) if voice_lines else ""
    )

    return Character(
        id=uuid.uuid4().hex,
        name=disp or "Cast",
        identity=_clip(identity_block, _MAX_FIELD),
        visual_style=_clip(visual_style, _MAX_FIELD),
        negatives=_clip(negatives, _MAX_FIELD),
        reference_image_rel="",
        use_default_voice=True,
        pyttsx3_voice_id="",
        kokoro_voice="",
        voice_instruction=_clip(voice_instruction, _MAX_FIELD),
        elevenlabs_voice_id="",
    )


def _deterministic_character_id(*, name: str, video_format: str, headline_seed: str = "") -> str:
    """
    Stable per-(name, format) hex id used so re-running the same generated cast
    upserts existing entries instead of duplicating them in the global store.
    """
    seed = f"{(name or '').strip().lower()}|{normalize_video_format(video_format)}|{(headline_seed or '').strip()}"
    digest = zlib.adler32(seed.encode("utf-8", errors="ignore")) & 0xFFFFFFFF
    base = uuid.uuid5(uuid.NAMESPACE_DNS, seed).hex
    return f"{digest:08x}{base[:24]}"


def cast_to_characters(
    *,
    cast: list[dict[str, Any]],
    video_format: str,
    headline_seed: str = "",
) -> list[Character]:
    """
    Convert a generated cast list into one full :class:`Character` per cast member.

    Mirrors the Characters tab schema (identity, visual_style, negatives, voice_instruction)
    so the auto-generated cast reaches feature parity with hand-authored characters.

    Stable IDs are derived from ``(name, video_format, headline_seed)`` so the same generated
    cast does not duplicate on subsequent runs.
    """
    out: list[Character] = []
    seen_ids: set[str] = set()
    vf = normalize_video_format(video_format)
    for c in cast:
        if not isinstance(c, dict):
            continue
        name = _clip(str(c.get("name") or ""), _MAX_NAME)
        if not name:
            continue
        identity_raw = str(c.get("identity") or "").strip()
        role = str(c.get("role") or "").strip()
        if role and identity_raw and not identity_raw.lower().startswith(role.lower()):
            identity = f"{role}: {identity_raw}"
        elif role and not identity_raw:
            identity = role
        else:
            identity = identity_raw
        cid = _deterministic_character_id(name=name, video_format=vf, headline_seed=headline_seed)
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        out.append(
            Character(
                id=cid,
                name=name,
                identity=_clip(identity, _MAX_FIELD),
                visual_style=_clip(str(c.get("visual_style") or ""), _MAX_FIELD),
                negatives=_clip(str(c.get("negatives") or ""), _MAX_FIELD),
                reference_image_rel="",
                use_default_voice=True,
                pyttsx3_voice_id="",
                kokoro_voice="",
                voice_instruction=_clip(str(c.get("voice_instruction") or ""), _MAX_FIELD),
                elevenlabs_voice_id="",
            )
        )
    return out


def merge_cast_into_store(
    *,
    cast: list[dict[str, Any]],
    video_format: str,
    headline_seed: str = "",
) -> list[Character]:
    """
    Upsert auto-generated cast members into the global ``characters.json`` store.

    Returns the list of :class:`Character` objects that ended up persisted (the cast members
    themselves; the rest of the store is untouched). Idempotent — calling twice with the same
    inputs results in updates, not duplicates, because IDs are deterministic.
    """
    new_chars = cast_to_characters(
        cast=cast, video_format=video_format, headline_seed=headline_seed
    )
    if not new_chars:
        return []
    existing = load_all()
    by_id = {c.id: c for c in existing}
    for ch in new_chars:
        by_id[ch.id] = ch
    save_all(sorted(by_id.values(), key=lambda x: x.name.lower()))
    return new_chars


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
