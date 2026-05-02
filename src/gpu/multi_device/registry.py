from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.models.model_manager import model_options

ShardStatus = Literal["stub", "experimental", "supported"]


def normalize_hub_repo_id(repo_id: str) -> str:
    """Normalize Hugging Face repo ids used as registry keys (matches ``clips._norm_repo_id``)."""
    return (repo_id or "").strip().lower()


@dataclass(frozen=True)
class ShardRegistryRow:
    repo_norm: str
    role: Literal["script", "image", "video", "voice"]
    integration_surface: str
    #: ``legacy_single_device`` — no intra-model shard; ``accelerate_llm_balanced`` — causal LM slicing;
    #: ``diffusion_peer_modules`` — move listed diffusers submodule attrs to peer GPU;
    #: ``unsupported_intra_shard`` — upstream stack cannot shard (still listed for completeness).
    vram_first_strategy: Literal[
        "legacy_single_device", "accelerate_llm_balanced", "diffusion_peer_modules", "unsupported_intra_shard"
    ]
    quant_gates: str
    status: ShardStatus
    llm_allow_accelerate_multi: bool
    diffusion_peer_modules: tuple[str, ...]


def _surface_for(kind: str) -> str:
    return {
        "script": "src/content/brain.py:load_causal_lm_from_pretrained",
        "image": "src/render/artist.py:_place_pipe_on_device",
        "video": "src/render/clips.py:place_diffusion_pipeline",
        "voice": "src/speech/tts_kokoro_moss.py",
    }.get(kind, kind)


_SHARD_ROWS: dict[tuple[str, str], ShardRegistryRow] | None = None


def _baseline_row(kind: str, repo_id: str) -> ShardRegistryRow:
    rn = normalize_hub_repo_id(repo_id)
    if kind == "script":
        strat: Literal[
            "legacy_single_device",
            "accelerate_llm_balanced",
            "diffusion_peer_modules",
            "unsupported_intra_shard",
        ] = "accelerate_llm_balanced"
    elif kind in ("image", "video"):
        strat = "diffusion_peer_modules"
    else:
        strat = "legacy_single_device"
    llm_allow = kind == "script"
    peer: tuple[str, ...] = ()
    st: ShardStatus = "stub"
    return ShardRegistryRow(
        repo_norm=rn,
        role=kind,  # type: ignore[arg-type]
        integration_surface=_surface_for(kind),
        vram_first_strategy=strat,
        quant_gates="bnb_single_gpu:int8_nf4_gate",
        status=st,
        llm_allow_accelerate_multi=llm_allow,
        diffusion_peer_modules=peer,
    )


def _build_registry() -> dict[tuple[str, str], ShardRegistryRow]:
    out: dict[tuple[str, str], ShardRegistryRow] = {}

    for opt in model_options():
        row = _baseline_row(opt.kind, opt.repo_id)
        out[(opt.kind, row.repo_norm)] = row

    def _upd(key_kind: str, repo: str, **kwargs: object) -> None:
        rk = normalize_hub_repo_id(repo)
        old = out[(key_kind, rk)]
        out[(key_kind, rk)] = ShardRegistryRow(
            repo_norm=old.repo_norm,
            role=old.role,
            integration_surface=old.integration_surface,
            vram_first_strategy=kwargs.get("vram_first_strategy", old.vram_first_strategy),  # type: ignore[arg-type]
            quant_gates=str(kwargs.get("quant_gates", old.quant_gates)),
            status=kwargs.get("status", old.status),  # type: ignore[arg-type]
            llm_allow_accelerate_multi=bool(kwargs.get("llm_allow_accelerate_multi", old.llm_allow_accelerate_multi)),
            diffusion_peer_modules=tuple(kwargs.get("diffusion_peer_modules", old.diffusion_peer_modules)),  # type: ignore[arg-type]
        )

    _upd(
        "script",
        "deepseek-ai/DeepSeek-V3",
        vram_first_strategy="legacy_single_device",
        llm_allow_accelerate_multi=False,
        status="experimental",
    )
    _upd(
        "script",
        "sophosympatheia/Midnight-Miqu-70B-v1.5",
        status="experimental",
        vram_first_strategy="accelerate_llm_balanced",
    )

    for rid in (
        "black-forest-labs/FLUX.1.1-pro-ultra",
        "black-forest-labs/FLUX.1-dev",
        "black-forest-labs/FLUX.1-schnell",
    ):
        _upd(
            "image",
            rid,
            diffusion_peer_modules=("text_encoder", "text_encoder_2"),
            status="experimental",
            vram_first_strategy="diffusion_peer_modules",
        )
    for rid in (
        "stabilityai/stable-diffusion-3.5-large",
        "stabilityai/stable-diffusion-3.5-medium",
        "stabilityai/stable-diffusion-3.5-large-turbo",
    ):
        _upd(
            "image",
            rid,
            diffusion_peer_modules=("text_encoder", "text_encoder_2", "text_encoder_3"),
            status="experimental",
            vram_first_strategy="diffusion_peer_modules",
        )

    for rid in (
        "Wan-AI/Wan2.2-T2V-A14B-Diffusers",
        "genmo/mochi-1.5-final",
        "THUDM/CogVideoX-5b",
        "Tencent/HunyuanVideo",
        "Lightricks/LTX-2",
    ):
        _upd(
            "video",
            rid,
            diffusion_peer_modules=("text_encoder", "text_encoder_2"),
            status="experimental",
            vram_first_strategy="diffusion_peer_modules",
        )

    _upd(
        "voice",
        "hexgrad/Kokoro-82M",
        vram_first_strategy="unsupported_intra_shard",
        status="stub",
        llm_allow_accelerate_multi=False,
    )
    _upd(
        "voice",
        "OpenMOSS-Team/MOSS-VoiceGenerator",
        vram_first_strategy="legacy_single_device",
        status="experimental",
    )

    for kind in ("script", "image", "video", "voice"):
        fk = normalize_hub_repo_id(f"__fallback__::{kind}")
        out[(kind, fk)] = ShardRegistryRow(
            repo_norm=fk,
            role=kind,  # type: ignore[arg-type]
            integration_surface=_surface_for(kind),
            vram_first_strategy="legacy_single_device",
            quant_gates="unknown_id_conservative_legacy",
            status="stub",
            llm_allow_accelerate_multi=kind == "script",
            diffusion_peer_modules=(),
        )

    return out


def _registry_cache() -> dict[tuple[str, str], ShardRegistryRow]:
    global _SHARD_ROWS
    if _SHARD_ROWS is None:
        _SHARD_ROWS = _build_registry()
    return _SHARD_ROWS


def lookup_shard_row(*, role: str, repo_id: str) -> ShardRegistryRow:
    rk = normalize_hub_repo_id(repo_id)
    k = (role, rk)
    reg = _registry_cache()
    if k in reg:
        return reg[k]
    fk = normalize_hub_repo_id(f"__fallback__::{role}")
    return reg[(role, fk)]


def all_curated_shard_rows() -> tuple[ShardRegistryRow, ...]:
    """Expose registry rows omitting synthetic ``__fallback__`` keys."""
    reg = _registry_cache()
    rows = [row for (_, key_norm), row in reg.items() if "__fallback__" not in key_norm]
    return tuple(sorted(rows, key=lambda r: (r.role, r.repo_norm)))
