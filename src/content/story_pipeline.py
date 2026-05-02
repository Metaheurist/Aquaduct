"""
Multi-stage LLM refinement for video scripts (VideoPackage), keyed by video_format.

Stages run after the initial generate_script() pass when story_multistage_enabled is on.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from debug import dprint

from src.content.brain import (
    VideoPackage,
    _dispose_causal_lm_pair,
    _generate_with_loaded_causal_lm,
    _load_causal_lm_pair,
    video_package_from_llm_output,
)
from src.core.config import AppSettings, VIDEO_FORMATS

from src.runtime.pipeline_notice import emit_pipeline_notice

SCRIPT_MIN_TOTAL_WORDS = 200
SCRIPT_MIN_SEGMENTS = 8

_REFINEMENT_JSON_REPAIR_PREFIX = (
    "Convert the following model output into ONE valid JSON object only for a vertical video script. "
    "Required keys: title (string), description (string), hashtags (array of strings), hook (string), "
    "segments (array of objects with narration, visual_prompt, on_screen_text), cta (string). "
    "Use double quotes for JSON strings. Output ONLY the JSON object — no markdown fences, no commentary.\n\n"
    "---BEGIN MODEL OUTPUT---\n"
)

StageKind = Literal["llm_full_json", "elaboration_gate"]


def package_to_json_text(pkg: VideoPackage) -> str:
    d = {
        "title": pkg.title,
        "description": pkg.description,
        "hashtags": list(pkg.hashtags),
        "hook": pkg.hook,
        "cta": pkg.cta,
        "segments": [
            {
                "narration": s.narration,
                "visual_prompt": s.visual_prompt,
                "on_screen_text": s.on_screen_text,
            }
            for s in pkg.segments
        ],
    }
    return json.dumps(d, ensure_ascii=False, indent=2)


def narration_word_count(pkg: VideoPackage) -> int:
    return len(pkg.narration_text().split())


def _common_json_rules() -> str:
    return (
        "Respond with ONLY a single JSON object — no preamble, no trailing prose.\n"
        "Keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Rules: TTS reads hook, each narration, and cta — only speakable words there; "
        "put staging only in visual_prompt. title <= 80 chars. hashtags: 15-30 strings.\n"
        "Avoid markdown except optional ```json fence.\n"
    )


def _ctx_block(web_digest: str, reference_notes: str) -> str:
    w = (web_digest or "").strip()[:8000]
    r = (reference_notes or "").strip()[:4000]
    parts = []
    if w:
        parts.append("Supplemental web / search context (verify facts; prefer article excerpt when it conflicts):\n" + w)
    if r:
        parts.append("Reference images / style cues (use to inform visual_prompt mood and composition, not literal copy):\n" + r)
    return ("\n\n".join(parts) + "\n\n") if parts else ""


def _prompt_news_beats(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    arc = (
        "Enforce a clear information arc across segments: hook tied to real topics → context → "
        "concrete facts/beats → why it matters → CTA in host voice.\n"
        "Each segment must add new substance (fact, stake, or angle).\n"
    )
    return (
        f"You revise short-form NEWS / HEADLINE vertical scripts (video_format={vf!r}).\n"
        f"{arc}"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Current script JSON (rewrite completely if needed, preserve factual intent):\n"
        f"{body}\n"
    )


def _prompt_news_policy(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    return (
        "You are a safety and quality editor for short-form news video.\n"
        "Remove or rephrase slurs, hate, or harassment. Hedge uncertain claims (\"reports say\", \"if confirmed\").\n"
        "Keep host-in-character delivery. Do not add new unverified specifics.\n"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Script JSON:\n"
        f"{body}\n"
    )


def _prompt_news_clarity(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    return (
        "Tighten spoken lines for teleprompter/TTS: shorter sentences, clearer emphasis, no stage directions in narration.\n"
        "Keep visual_prompt concrete (subject, setting, one action, 9:16).\n"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Script JSON:\n"
        f"{body}\n"
    )


def _prompt_health_beats(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    arc = (
        "Enforce a clear wellness-education arc: caring hook → context → concrete tips or general condition facts → "
        "when to seek professional care → CTA with disclaimer in clinician voice.\n"
        "Educational tone only — not personal medical advice.\n"
    )
    return (
        f"You revise short-form HEALTH / WELLNESS education vertical scripts (video_format={vf!r}).\n"
        f"{arc}"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Current script JSON (rewrite completely if needed, preserve educational intent):\n"
        f"{body}\n"
    )


def _prompt_health_policy(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    return (
        "You are a medical-safety and quality editor for wellness education shorts.\n"
        "Remove or rephrase: personal diagnosis of the viewer, medication start/stop/change instructions, dosing, "
        "graphic injury or procedure detail, fear-mongering, miracle-cure claims.\n"
        "Add hedging where claims are uncertain. Keep clinician-in-character delivery. Do not add new clinical specifics beyond sources.\n"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Script JSON:\n"
        f"{body}\n"
    )


def _prompt_health_clarity(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    return (
        "Tighten clinician lines for teleprompter/TTS: shorter sentences, warm clear emphasis, no stage directions in narration.\n"
        "Keep visual_prompt concrete (teaching moment, diagram, calm clinical setting, one action, 9:16) — no gore, no readable long text.\n"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Script JSON:\n"
        f"{body}\n"
    )


def _prompt_creepypasta_beats(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    arc = (
        "Enforce a clear horror-fiction arc: uneasy hook → rising dread → twist/reveal → aftershock → CTA in narrator voice.\n"
        "Fiction only — do not frame as true crime or real events.\n"
    )
    return (
        f"You revise short-form CREEPYPASTA / horror-fiction vertical scripts (video_format={vf!r}).\n"
        f"{arc}"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Current script JSON (rewrite completely if needed, preserve fictional intent):\n"
        f"{body}\n"
    )


def _prompt_creepypasta_policy(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    return (
        "You are a safety editor for fictional horror shorts.\n"
        "Remove slurs, hate, harassment, sexual violence, glorification of self-harm, and graphic gore instructions.\n"
        "Keep dread atmospheric; hedge any line that could be read as a real threat toward a real person.\n"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Script JSON:\n"
        f"{body}\n"
    )


def _prompt_creepypasta_clarity(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    return (
        "Tighten narrator lines for TTS: shorter sentences, slower dread rhythm where needed, no stage directions in narration.\n"
        "Keep visual_prompt concrete (silhouettes, lighting, setting, one uncanny action, 9:16) — avoid readable wall text.\n"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Script JSON:\n"
        f"{body}\n"
    )


def _prompt_comedy_dialogue(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    return (
        f"You revise CARTOON / COMEDY vertical scripts (video_format={vf!r}).\n"
        "Improve character dialogue balance: distinct voices, callbacks, setup→punch per beat where possible.\n"
        "Spoken fields must stay in-character; no camera notes in narration.\n"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Script JSON:\n"
        f"{body}\n"
    )


def _prompt_comedy_pacing(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    return (
        f"You revise pacing for meme/Vine-style vertical comedy (video_format={vf!r}).\n"
        "Accelerate weak beats; ensure escalation toward a strong peak; land a clear payoff.\n"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Script JSON:\n"
        f"{body}\n"
    )


def _prompt_comedy_policy(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    return (
        "You are a policy editor for comedy shorts. Remove slurs and targeted harassment; keep satire playful.\n"
        "Do not imitate real celebrities or trademarked characters by name.\n"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Script JSON:\n"
        f"{body}\n"
    )


def _prompt_comedy_punchline(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    return (
        f"Final polish for comedy verticals (video_format={vf!r}).\n"
        "Strengthen the final beats and CTA; ensure the biggest joke or twist lands cleanly.\n"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Script JSON:\n"
        f"{body}\n"
    )


def _prompt_elaboration(pkg: VideoPackage, web_digest: str, reference_notes: str, vf: str) -> str:
    body = package_to_json_text(pkg)
    ctx = _ctx_block(web_digest, reference_notes)
    return (
        f"The script is too short for a ~75–95s vertical video (video_format={vf!r}).\n"
        f"Expand to at least {SCRIPT_MIN_TOTAL_WORDS} spoken words total (hook + segment narrations + cta) "
        f"and at least {SCRIPT_MIN_SEGMENTS} segments.\n"
        "Add beats that introduce new facts, jokes, or stakes — not filler transitions.\n"
        f"{_common_json_rules()}\n"
        f"{ctx}"
        "Script JSON (expand):\n"
        f"{body}\n"
    )


@dataclass(frozen=True)
class _StageSpec:
    id: str
    label: str
    kind: StageKind
    prompt_fn: Callable[[VideoPackage, str, str, str], str] | None = None


def _stages_for_format(vf: str) -> tuple[_StageSpec, ...]:
    v = (vf or "news").strip().lower()
    if v in ("news", "explainer"):
        return (
            _StageSpec("beat_structure", "Story beats & arc", "llm_full_json", _prompt_news_beats),
            _StageSpec("policy", "Safety & hedging", "llm_full_json", _prompt_news_policy),
            _StageSpec("elaboration", "Length & elaboration", "elaboration_gate", None),
            _StageSpec("clarity", "Clarity & TTS", "llm_full_json", _prompt_news_clarity),
        )
    if v == "health_advice":
        return (
            _StageSpec("beat_structure", "Wellness arc & education", "llm_full_json", _prompt_health_beats),
            _StageSpec("policy", "Medical safety & hedging", "llm_full_json", _prompt_health_policy),
            _StageSpec("elaboration", "Length & elaboration", "elaboration_gate", None),
            _StageSpec("clarity", "Clarity & TTS", "llm_full_json", _prompt_health_clarity),
        )
    if v == "cartoon":
        return (
            _StageSpec("dialogue", "Dialogue & characters", "llm_full_json", _prompt_comedy_dialogue),
            _StageSpec("pacing", "Pacing & escalation", "llm_full_json", _prompt_comedy_pacing),
            _StageSpec("policy", "Safety polish", "llm_full_json", _prompt_comedy_policy),
            _StageSpec("elaboration", "Length & elaboration", "elaboration_gate", None),
            _StageSpec("punchline", "Punchline polish", "llm_full_json", _prompt_comedy_punchline),
        )
    if v == "creepypasta":
        return (
            _StageSpec("beats", "Horror arc & dread", "llm_full_json", _prompt_creepypasta_beats),
            _StageSpec("policy", "Safety polish", "llm_full_json", _prompt_creepypasta_policy),
            _StageSpec("elaboration", "Length & elaboration", "elaboration_gate", None),
            _StageSpec("clarity", "Clarity & TTS", "llm_full_json", _prompt_creepypasta_clarity),
        )
    # unhinged
    return (
        _StageSpec("dialogue", "Dialogue & chaos", "llm_full_json", _prompt_comedy_dialogue),
        _StageSpec("pacing", "Escalation & peak", "llm_full_json", _prompt_comedy_pacing),
        _StageSpec("policy", "Safety polish", "llm_full_json", _prompt_comedy_policy),
        _StageSpec("elaboration", "Length & elaboration", "elaboration_gate", None),
        _StageSpec("punchline", "Landing the bit", "llm_full_json", _prompt_comedy_punchline),
    )


def refinement_stage_ids_for_format(video_format: str) -> list[str]:
    return [s.id for s in _stages_for_format(video_format)]


def all_video_formats_have_refinement_stages() -> bool:
    return all(len(_stages_for_format(v)) > 0 for v in VIDEO_FORMATS)


def _maybe_elaboration(
    pkg: VideoPackage,
    *,
    video_format: str,
    model_id: str,
    web_digest: str,
    reference_notes: str,
    try_llm_4bit: bool,
    on_llm_task: Callable[[str, int, str], None] | None,
    stage_idx: int,
    stage_total: int,
    app_settings: AppSettings | None = None,
    llm_cuda_device_index: int | None = None,
    llm_holder: dict[str, Any],
) -> VideoPackage:
    words = narration_word_count(pkg)
    nseg = len(pkg.segments)
    if words >= SCRIPT_MIN_TOTAL_WORDS and nseg >= SCRIPT_MIN_SEGMENTS:
        return pkg
    vf = (video_format or "news").strip().lower()

    def _emit(task: str, pct: int, msg: str) -> None:
        if not on_llm_task:
            return
        span = max(1, stage_total)
        base = int(100 * stage_idx / span)
        inner = max(0, min(100, int(pct)))
        overall = base + int(inner / span)
        on_llm_task(task, overall, f"Elaboration: {msg}")

    prompt = _prompt_elaboration(pkg, web_digest, reference_notes, vf)
    try:
        if llm_holder.get("model") is None:
            tok, mod = _load_causal_lm_pair(
                model_id,
                on_llm_task=_emit,
                try_llm_4bit=try_llm_4bit,
                llm_cuda_device_index=llm_cuda_device_index,
                inference_settings=app_settings,
            )
            llm_holder["tokenizer"] = tok
            llm_holder["model"] = mod
            llm_holder["hub_model_id"] = str(model_id or "").strip()
        raw = _generate_with_loaded_causal_lm(
            llm_holder["model"],
            llm_holder["tokenizer"],
            model_id,
            prompt,
            on_llm_task=_emit,
            max_new_tokens=2048,
            inference_settings=app_settings,
        )
        try:
            return video_package_from_llm_output(raw)
        except (json.JSONDecodeError, ValueError):
            repair_prompt = _REFINEMENT_JSON_REPAIR_PREFIX + raw.strip()[:14000]
            raw_fix = _generate_with_loaded_causal_lm(
                llm_holder["model"],
                llm_holder["tokenizer"],
                model_id,
                repair_prompt,
                on_llm_task=_emit,
                max_new_tokens=2048,
                inference_settings=app_settings,
            )
            return video_package_from_llm_output(raw_fix)
    except Exception as e:
        dprint("story_pipeline", "elaboration failed", str(e))
        return pkg


def run_multistage_refinement(
    pkg: VideoPackage,
    *,
    video_format: str,
    model_id: str,
    web_digest: str = "",
    reference_notes: str = "",
    try_llm_4bit: bool = True,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    app_settings: AppSettings | None = None,
    llm_cuda_device_index: int | None = None,
    llm_holder: dict[str, Any] | None = None,
) -> VideoPackage:
    """
    Run format-specific refinement stages. Loads the causal LM once and reuses it across LLM stages
    to avoid VRAM churn from repeated full reloads.

    If ``llm_holder`` is provided (from the pipeline runner), refinement reuses shared weights instead
    of owning its own load/dispose lifecycle.
    """
    stages = _stages_for_format(video_format)
    total = len(stages)
    cur = pkg
    external_holder = llm_holder is not None
    llm_holder = llm_holder if llm_holder is not None else {"tokenizer": None, "model": None, "hub_model_id": ""}
    refinement_json_notice_sent = False

    try:
        for i, spec in enumerate(stages):
            if spec.kind == "elaboration_gate":
                cur = _maybe_elaboration(
                    cur,
                    video_format=video_format,
                    model_id=model_id,
                    web_digest=web_digest,
                    reference_notes=reference_notes,
                    try_llm_4bit=try_llm_4bit,
                    on_llm_task=on_llm_task,
                    stage_idx=i,
                    stage_total=total,
                    app_settings=app_settings,
                    llm_cuda_device_index=llm_cuda_device_index,
                    llm_holder=llm_holder,
                )
                continue
            assert spec.prompt_fn is not None
            prompt = spec.prompt_fn(cur, web_digest, reference_notes, (video_format or "news").strip().lower())

            def _emit(task: str, pct: int, msg: str) -> None:
                if not on_llm_task:
                    return
                span = max(1, total)
                base = int(100 * i / span)
                inner = max(0, min(100, int(pct)))
                overall = base + int(inner / span)
                on_llm_task(task, overall, f"{spec.label}: {msg}")

            try:
                if llm_holder.get("model") is None:
                    tok, mod = _load_causal_lm_pair(
                        model_id,
                        on_llm_task=_emit,
                        try_llm_4bit=try_llm_4bit,
                        llm_cuda_device_index=llm_cuda_device_index,
                        inference_settings=app_settings,
                    )
                    llm_holder["tokenizer"] = tok
                    llm_holder["model"] = mod
                    llm_holder["hub_model_id"] = str(model_id or "").strip()
                raw = _generate_with_loaded_causal_lm(
                    llm_holder["model"],
                    llm_holder["tokenizer"],
                    model_id,
                    prompt,
                    on_llm_task=_emit,
                    max_new_tokens=2048,
                    inference_settings=app_settings,
                )
                try:
                    cur = video_package_from_llm_output(raw)
                except (json.JSONDecodeError, ValueError):
                    repair_prompt = _REFINEMENT_JSON_REPAIR_PREFIX + raw.strip()[:14000]
                    raw_fix = _generate_with_loaded_causal_lm(
                        llm_holder["model"],
                        llm_holder["tokenizer"],
                        model_id,
                        repair_prompt,
                        on_llm_task=_emit,
                        max_new_tokens=2048,
                        inference_settings=app_settings,
                    )
                    cur = video_package_from_llm_output(raw_fix)
            except (json.JSONDecodeError, ValueError) as e:
                dprint("story_pipeline", f"stage {spec.id} failed", str(e))
                if not refinement_json_notice_sent:
                    emit_pipeline_notice(
                        "Script refinement",
                        "A refinement stage did not return usable JSON (including repair); continuing with the previous draft.",
                    )
                    refinement_json_notice_sent = True
            except Exception as e:
                dprint("story_pipeline", f"stage {spec.id} failed", str(e))
    finally:
        had_llm = llm_holder.get("model") is not None
        if had_llm and not external_holder:
            _dispose_causal_lm_pair(llm_holder["model"], llm_holder["tokenizer"])
        if had_llm and not external_holder:
            try:
                from src.util.memory_budget import release_between_stages

                release_between_stages(
                    "after_multistage_refinement_llm",
                    cuda_device_index=llm_cuda_device_index,
                    variant="prepare_diffusion",
                )
            except Exception:
                pass

    return cur
