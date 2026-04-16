from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .utils_vram import cleanup_vram, vram_guard
from .personalities import PersonalityPreset, get_personality_by_id
from .config import BrandingSettings
from .branding_video import palette_prompt_suffix, video_style_strength


@dataclass(frozen=True)
class ScriptSegment:
    narration: str
    visual_prompt: str
    on_screen_text: str | None = None


@dataclass(frozen=True)
class VideoPackage:
    title: str
    description: str
    hashtags: list[str]
    hook: str
    segments: list[ScriptSegment]
    cta: str

    def narration_text(self) -> str:
        parts: list[str] = []
        if self.hook.strip():
            parts.append(self.hook.strip())
        parts.extend(s.narration.strip() for s in self.segments if s.narration.strip())
        if self.cta.strip():
            parts.append(self.cta.strip())
        return " ".join(parts).strip()


def _extract_json(text: str) -> dict[str, Any]:
    """
    Best-effort JSON extraction from a model response that may include prose.
    """
    # Prefer fenced block
    m = re.search(r"```json\s*([\s\S]+?)\s*```", text, flags=re.IGNORECASE)
    if m:
        return json.loads(m.group(1))

    # Otherwise try first {...} span
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("No JSON object found in model output.")


def _normalize_hashtags(tags: list[Any]) -> list[str]:
    out: list[str] = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + t.lstrip("#")
        # Keep TikTok-friendly tags short-ish
        t = re.sub(r"\s+", "", t)
        if 2 <= len(t) <= 40:
            out.append(t)
    # de-dupe while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for t in out:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    return deduped[:30]


def _to_package(data: dict[str, Any]) -> VideoPackage:
    title = str(data.get("title", "")).strip() or "AI Tool Review"
    description = str(data.get("description", "")).strip()
    if not description:
        description = "Quick breakdown of a new AI tool release: what it does, why it matters, and who should try it."

    hashtags = _normalize_hashtags(data.get("hashtags", []) if isinstance(data.get("hashtags"), list) else [])
    if not hashtags:
        hashtags = ["#AI", "#AITools", "#TechTok", "#Productivity", "#AInews"]

    hook = str(data.get("hook", "")).strip()
    cta = str(data.get("cta", "")).strip() or "Follow for daily AI tool drops and fast reviews."

    segs_raw = data.get("segments", [])
    segments: list[ScriptSegment] = []
    if isinstance(segs_raw, list):
        for s in segs_raw:
            if not isinstance(s, dict):
                continue
            narration = str(s.get("narration", "")).strip()
            visual = str(s.get("visual_prompt", "")).strip()
            on_screen = s.get("on_screen_text", None)
            on_screen_text = str(on_screen).strip() if isinstance(on_screen, str) and on_screen.strip() else None
            if narration and visual:
                segments.append(ScriptSegment(narration=narration, visual_prompt=visual, on_screen_text=on_screen_text))

    if not segments:
        # Minimal fallback structure
        segments = [
            ScriptSegment(
                narration="Here’s the new AI tool everyone’s testing—and why it’s useful.",
                visual_prompt="high-contrast cyberpunk UI, neon holographic interface, close-up, sharp, 9:16 composition",
                on_screen_text="NEW AI TOOL",
            )
        ]

    return VideoPackage(
        title=title,
        description=description,
        hashtags=hashtags,
        hook=hook,
        segments=segments,
        cta=cta,
    )


def _prompt_for_items(
    headlines: list[dict[str, str]],
    topic_tags: list[str] | None,
    personality: PersonalityPreset,
    branding: BrandingSettings | None = None,
) -> str:
    # Keep it stable for JSON parsing.
    tags = [t.strip() for t in (topic_tags or []) if t and t.strip()]
    tag_line = f"Topic tags (must strongly influence the tool choice/angle): {json.dumps(tags, ensure_ascii=False)}\n" if tags else ""
    personality_block = (
        "Tone/personality:\n"
        f"- {personality.label}\n"
        f"- {personality.description}\n"
        "Style rules:\n"
        + "\n".join(f"- {r}" for r in personality.style_rules)
        + "\nDo/Don't:\n"
        + "\n".join(f"- {r}" for r in personality.do_dont)
        + "\n"
    )

    style_suffix = ""
    if branding and bool(getattr(branding, "video_style_enabled", False)):
        strength = video_style_strength(branding)
        suf = palette_prompt_suffix(branding)
        if suf:
            style_suffix = (
                "Visual palette guidance:\n"
                f"- Strength: {strength}\n"
                f"- {suf}\n"
            )
    return (
        "You are a viral short-form scriptwriter focused on AI tool reviews.\n"
        "Write a ~50 second vertical video script with 6-10 few-second beats.\n"
        "Style: punchy, factual, no fluff. Visual style: high-contrast cyberpunk.\n"
        "Enforce this structure (keep it tight):\n"
        "- Hook (0-2s): one punchy line\n"
        "- Context (2-6s): what it is / what's new\n"
        "- Key points (6-20s): 2-3 concrete points\n"
        "- Why it matters (20-30s): practical impact / who should care\n"
        "- Close/CTA (last 2s): short follow/subscribe style line\n"
        "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Constraints:\n"
        "- narration total ~120-150 words\n"
        "- title <= 80 chars\n"
        "- hashtags: 15-30 items, each like \"#AITools\"\n"
        "- mention the tool name early\n"
        "- avoid markdown except optional ```json fence\n"
        "\n"
        f"{personality_block}"
        f"{style_suffix}"
        f"{tag_line}"
        f"Headlines (pick ONE main tool release to review): {json.dumps(headlines, ensure_ascii=False)}\n"
    )


def enforce_arc(pkg: VideoPackage) -> VideoPackage:
    """
    Best-effort post-processor to ensure the script includes context + why-it-matters beats.
    We don't require the model to label beats; we inject minimal beats if missing.
    """
    try:
        segs = list(pkg.segments or [])
    except Exception:
        return pkg

    # Heuristics: look for context/why language.
    all_text = " ".join([(pkg.hook or "")] + [s.narration for s in segs] + [(pkg.cta or "")]).lower()
    has_context = any(k in all_text for k in ("here’s what it is", "what it is", "it lets you", "it helps you", "it does", "context"))
    has_why = any(k in all_text for k in ("why it matters", "so what", "this matters because", "impact", "useful because", "the takeaway"))

    insertions: list[ScriptSegment] = []
    if not has_context:
        insertions.append(
            ScriptSegment(
                narration="Quick context: here’s what it is and what just changed.",
                visual_prompt="clean cyberpunk infographic panel, clear labels, high contrast, 9:16",
                on_screen_text="CONTEXT",
            )
        )
    if not has_why:
        insertions.append(
            ScriptSegment(
                narration="Why it matters: it saves time on a real workflow—if you use it the right way.",
                visual_prompt="cyberpunk timeline + impact icons, neon accents, high contrast, 9:16",
                on_screen_text="WHY IT MATTERS",
            )
        )

    if not insertions:
        return pkg

    # Place insertions after first segment if possible.
    out: list[ScriptSegment] = []
    if segs:
        out.append(segs[0])
        out.extend(insertions)
        out.extend(segs[1:])
    else:
        out = insertions

    # Keep overall beat count sane.
    out = out[: max(6, min(10, len(out)))]
    return VideoPackage(
        title=pkg.title,
        description=pkg.description,
        hashtags=list(pkg.hashtags),
        hook=pkg.hook,
        segments=out,
        cta=pkg.cta,
    )


def _generate_with_transformers(model_id: str, prompt: str) -> str:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
    )

    try:
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            quantization_config=bnb,
            device_map="auto",
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
        )
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            quantization_config=bnb,
            device_map="auto",
            torch_dtype=torch.float16,
        )

    # Simple chat-ish formatting without requiring tokenizer chat template support.
    full = f"### Instruction:\n{prompt}\n\n### Response:\n"
    inputs = tokenizer(full, return_tensors="pt").to(model.device)

    with torch.inference_mode():
        out = model.generate(
            **inputs,
            max_new_tokens=650,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.08,
            eos_token_id=tokenizer.eos_token_id,
        )

    text = tokenizer.decode(out[0], skip_special_tokens=True)
    # Strip prompt echo if present
    if "### Response:" in text:
        text = text.split("### Response:", 1)[1].strip()

    # Cleanup aggressively (VRAM limited)
    del model
    del tokenizer
    cleanup_vram()
    return text


def generate_script(
    *,
    model_id: str,
    items: list[dict[str, str]],
    topic_tags: list[str] | None = None,
    personality_id: str = "neutral",
    branding: BrandingSettings | None = None,
) -> VideoPackage:
    """
    Generates a structured video package from scraped headlines/links.
    Tries local 4-bit transformers; falls back to a deterministic template if the model fails to load.
    """
    personality = get_personality_by_id(personality_id)
    prompt = _prompt_for_items(items, topic_tags, personality, branding=branding)

    with vram_guard():
        try:
            raw = _generate_with_transformers(model_id=model_id, prompt=prompt)
            data = _extract_json(raw)
            return _to_package(data)
        except Exception:
            # Fallback: minimal structured script without the LLM (keeps pipeline running).
            tool_title = (items[0].get("title") if items else "") or "New AI Tool"
            title = tool_title[:80]

            # Tone shaping for fallback
            if personality.id == "hype":
                hook = "Stop scrolling—this AI tool is actually insane."
                cta = "Follow for daily AI tool drops with real takeaways."
            elif personality.id == "analytical":
                hook = "Quick technical breakdown: a new AI tool just shipped."
                cta = "Follow for practical AI tooling breakdowns."
            elif personality.id == "comedic":
                hook = "Stop scrolling—your workflow is about to get bullied (in a good way)."
                cta = "Follow for daily AI tools, minus the cringe."
            elif personality.id == "skeptical":
                hook = "Before you believe the hype—here’s what this new AI tool really does."
                cta = "Follow for honest AI tool reviews and trade-offs."
            elif personality.id == "cozy":
                hook = "Hey—quick and simple: this new AI tool might save you time."
                cta = "Follow for friendly AI tool tips you can use today."
            elif personality.id == "urgent":
                hook = "Breaking: a new AI tool just dropped—here’s the fast rundown."
                cta = "Follow for daily AI news you can act on."
            elif personality.id == "contrarian":
                hook = "Hot take: this new AI tool is useful—but not for the reason you think."
                cta = "Follow for sharp AI tool takes with receipts."
            else:
                hook = "Stop scrolling—this new AI tool just dropped."
                cta = "Follow for daily AI tool reviews you can actually use."

            pkg = VideoPackage(
                title=title,
                description=f"Fast review: {tool_title}. What it does, who it’s for, and why it matters.",
                hashtags=[
                    "#AI",
                    "#AITools",
                    "#AInews",
                    "#Productivity",
                    "#TechTok",
                    "#Automation",
                    "#MachineLearning",
                    "#Startup",
                    "#NewApp",
                    "#ToolReview",
                    "#Cyberpunk",
                    "#FutureTech",
                    "#Tech",
                    "#Shorts",
                    "#TikTok",
                ],
                hook=hook,
                segments=[
                    ScriptSegment(
                        narration=f"Today’s drop: {tool_title}. Here’s the quick breakdown.",
                        visual_prompt="high-contrast cyberpunk city, neon UI overlay, holographic app panels, sharp, cinematic, 9:16",
                        on_screen_text="NEW TOOL DROP",
                    ),
                    ScriptSegment(
                        narration="What it does: it automates a boring workflow in seconds.",
                        visual_prompt="neon cyberpunk dashboard, glowing graphs, crisp UI, dark background, 9:16, high contrast",
                        on_screen_text="WHAT IT DOES",
                    ),
                    ScriptSegment(
                        narration="Who it’s for: creators, builders, and anyone who wants speed.",
                        visual_prompt="cyberpunk creator desk, neon lighting, holograms, tech aesthetic, 9:16",
                        on_screen_text="WHO IT’S FOR",
                    ),
                    ScriptSegment(
                        narration="My take: test it on one task today and keep the best results.",
                        visual_prompt="close-up neon terminal, glitch effect, futuristic UI, 9:16, sharp",
                        on_screen_text="QUICK TAKE",
                    ),
                ],
                cta=cta,
            )

            # Apply palette to fallback prompts (best-effort)
            if branding and bool(getattr(branding, "video_style_enabled", False)):
                suf = palette_prompt_suffix(branding)
                if suf:
                    pkg = VideoPackage(
                        title=pkg.title,
                        description=pkg.description,
                        hashtags=pkg.hashtags,
                        hook=pkg.hook,
                        segments=[
                            ScriptSegment(
                                narration=s.narration,
                                visual_prompt=(s.visual_prompt if "Palette:" in s.visual_prompt else f"{s.visual_prompt}, {suf}"),
                                on_screen_text=s.on_screen_text,
                            )
                            for s in pkg.segments
                        ],
                        cta=pkg.cta,
                    )
            # If tags are provided, append a couple as hashtags (best-effort).
            if topic_tags:
                extra = []
                for t in topic_tags:
                    t = re.sub(r"[^A-Za-z0-9]+", "", (t or "").strip())
                    if t:
                        extra.append("#" + t[:28])
                pkg = VideoPackage(
                    title=pkg.title,
                    description=pkg.description,
                    hashtags=(pkg.hashtags + extra)[:30],
                    hook=pkg.hook,
                    segments=pkg.segments,
                    cta=pkg.cta,
                )
            return pkg

