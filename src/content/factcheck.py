from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .brain import VideoPackage, ScriptSegment, _extract_json, load_causal_lm_from_pretrained
from src.core.models_dir import get_models_dir
from src.models.model_manager import resolve_pretrained_load_path


@dataclass(frozen=True)
class Claim:
    text: str
    kind: str  # number | superlative | absolute


# Note: don't use trailing \b because units like '%' aren't word chars.
_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|x|times|ms|s|sec|seconds|mins|minutes|hours|days|\$|usd|gb|mb|k)", re.IGNORECASE)
_SUPER_RE = re.compile(r"\b(first|only|best|fastest|biggest|most|least)\b", re.IGNORECASE)
_ABS_RE = re.compile(r"\b(always|never|guaranteed|proven|no one|everyone)\b", re.IGNORECASE)


def extract_claims(text: str) -> list[Claim]:
    t = " ".join((text or "").split()).strip()
    if not t:
        return []
    out: list[Claim] = []
    for m in _NUM_RE.finditer(t):
        out.append(Claim(text=m.group(0), kind="number"))
    for m in _SUPER_RE.finditer(t):
        out.append(Claim(text=m.group(0), kind="superlative"))
    for m in _ABS_RE.finditer(t):
        out.append(Claim(text=m.group(0), kind="absolute"))
    # de-dupe
    seen: set[tuple[str, str]] = set()
    dedup: list[Claim] = []
    for c in out:
        k = (c.text.lower(), c.kind)
        if k in seen:
            continue
        seen.add(k)
        dedup.append(c)
    return dedup[:40]


def _to_payload(pkg: VideoPackage) -> dict[str, Any]:
    return {
        "title": pkg.title,
        "description": pkg.description,
        "hashtags": list(pkg.hashtags),
        "hook": pkg.hook,
        "segments": [
            {"narration": s.narration, "visual_prompt": s.visual_prompt, "on_screen_text": s.on_screen_text}
            for s in (pkg.segments or [])
        ],
        "cta": pkg.cta,
    }


def _from_payload(d: dict[str, Any]) -> VideoPackage:
    segs: list[ScriptSegment] = []
    for s in d.get("segments", []) if isinstance(d.get("segments"), list) else []:
        if not isinstance(s, dict):
            continue
        narration = str(s.get("narration", "")).strip()
        visual = str(s.get("visual_prompt", "")).strip()
        on_screen = s.get("on_screen_text", None)
        on_screen_text = str(on_screen).strip() if isinstance(on_screen, str) and on_screen.strip() else None
        if narration and visual:
            segs.append(ScriptSegment(narration=narration, visual_prompt=visual, on_screen_text=on_screen_text))
    return VideoPackage(
        title=str(d.get("title", "")).strip() or "Short video",
        description=str(d.get("description", "")).strip(),
        hashtags=[str(x) for x in (d.get("hashtags", []) if isinstance(d.get("hashtags"), list) else []) if isinstance(x, str)],
        hook=str(d.get("hook", "")).strip(),
        segments=segs,
        cta=str(d.get("cta", "")).strip(),
    )


def rewrite_with_uncertainty(
    *,
    pkg: VideoPackage,
    article_text: str,
    sources: list[dict[str, str]],
    model_id: str,
    try_llm_4bit: bool = True,
    quant_mode: str | None = None,
) -> VideoPackage:
    """
    LLM-assisted safety rewrite: attribute numeric/strong claims when article text is thin,
    and soften absolutes/superlatives. Falls back to deterministic softening if LLM fails.
    """
    narration = pkg.narration_text()
    claims = extract_claims(narration)

    # If we don't have enough source text, bias toward uncertainty language.
    thin = len((article_text or "").strip()) < 800
    need = thin or any(c.kind != "number" for c in claims) or len(claims) >= 3

    if not need:
        return pkg

    # Try local LLM rewrite. Keep it strict JSON.
    model = None
    tokenizer = None
    try:
        import torch

        from src.models.hf_transformers_imports import causal_lm_stack

        _, AutoTokenizer, _ = causal_lm_stack()

        load_path = resolve_pretrained_load_path(model_id, models_dir=get_models_dir())
        tokenizer = AutoTokenizer.from_pretrained(load_path, use_fast=True, trust_remote_code=True)
        model = load_causal_lm_from_pretrained(
            load_path,
            try_4bit=bool(try_llm_4bit),
            on_status=None,
            quant_mode=quant_mode,
        )

        src_line = json.dumps(sources[:3], ensure_ascii=False)
        article_snip = (article_text or "")[:2400]
        payload = json.dumps(_to_payload(pkg), ensure_ascii=False)
        prompt = (
            "You are a careful editor. Rewrite the following short-form video script JSON to be fact-safe.\n"
            "Rules:\n"
            "- Keep the SAME structure and keys.\n"
            "- Keep it punchy but avoid absolutes and unsupported numbers.\n"
            "- If numbers/claims are not clearly supported by the provided article text, add attribution (\"according to\") or soften (\"reportedly\", \"early reports\").\n"
            "- Do not invent new facts.\n"
            "- Output STRICT JSON only.\n\n"
            f"SOURCES: {src_line}\n\n"
            f"ARTICLE_TEXT (snippet): {article_snip}\n\n"
            f"INPUT_JSON: {payload}\n"
        )

        full = f"### Instruction:\n{prompt}\n\n### Response:\n"
        inputs = tokenizer(full, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            out = model.generate(
                **inputs,
                max_new_tokens=750,
                do_sample=True,
                temperature=0.5,
                top_p=0.9,
                repetition_penalty=1.06,
                eos_token_id=tokenizer.eos_token_id,
            )
        text = tokenizer.decode(out[0], skip_special_tokens=True)
        if "### Response:" in text:
            text = text.split("### Response:", 1)[1].strip()
        data = _extract_json(text)
        # Build new package with safe rewrite; keep original hashtags if rewrite dropped them.
        out_pkg = _from_payload(data)
        if not out_pkg.hashtags:
            out_pkg = VideoPackage(
                title=out_pkg.title,
                description=out_pkg.description,
                hashtags=list(pkg.hashtags),
                hook=out_pkg.hook,
                segments=out_pkg.segments,
                cta=out_pkg.cta,
            )
        return out_pkg
    except Exception:
        pass
    finally:
        try:
            if model is not None:
                del model
            if tokenizer is not None:
                del tokenizer
            from src.util.utils_vram import cleanup_vram

            cleanup_vram()
        except Exception:
            pass

    # Deterministic fallback: soften absolutes + add attribution stub if thin.
    def soften(s: str) -> str:
        s = re.sub(_ABS_RE, "often", s)
        s = re.sub(_SUPER_RE, "one of the", s)
        return s

    hook = soften(pkg.hook)
    segs = [ScriptSegment(narration=soften(s.narration), visual_prompt=s.visual_prompt, on_screen_text=s.on_screen_text) for s in pkg.segments]
    cta = soften(pkg.cta)
    if thin:
        # Add a light attribution line early.
        if segs:
            segs.insert(
                1,
                ScriptSegment(
                    narration="According to early reports, here’s the key takeaway—keep an eye on updates.",
                    visual_prompt="cyberpunk news ticker, neon highlights, high contrast, 9:16",
                    on_screen_text="EARLY REPORTS",
                ),
            )
    return VideoPackage(
        title=pkg.title,
        description=pkg.description,
        hashtags=list(pkg.hashtags),
        hook=hook,
        segments=segs[:10],
        cta=cta,
    )

