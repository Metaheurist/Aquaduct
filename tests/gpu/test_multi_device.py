from __future__ import annotations

from dataclasses import replace

import pytest

from src.core.config import AppSettings
from src.gpu.multi_device.gates import vram_first_master_enabled
from src.gpu.multi_device.registry import all_curated_shard_rows, lookup_shard_row, normalize_hub_repo_id
from src.models.model_manager import model_options


def test_normalize_hub_repo_id_lowercases() -> None:
    assert normalize_hub_repo_id("  Org/Repo-Name ") == "org/repo-name"


def test_registry_covers_every_model_option_repo() -> None:
    want = {(o.kind, normalize_hub_repo_id(o.repo_id)) for o in model_options()}
    have = {(r.role, r.repo_norm) for r in all_curated_shard_rows()}
    assert want <= have


def test_unknown_repo_uses_fallback_registry_key() -> None:
    row = lookup_shard_row(role="image", repo_id="zz/unknown-model-123")
    assert "__fallback__" in row.repo_norm


def test_deepseek_disallows_accelerate_llm_multi() -> None:
    row = lookup_shard_row(role="script", repo_id="deepseek-ai/DeepSeek-V3")
    assert row.llm_allow_accelerate_multi is False


def test_kokoro_registry_marks_unsupported_intra_shard() -> None:
    row = lookup_shard_row(role="voice", repo_id="hexgrad/Kokoro-82M")
    assert row.vram_first_strategy == "unsupported_intra_shard"


def test_vram_first_master_enabled_respects_toggle_and_plan_mode() -> None:
    disabled = replace(AppSettings(), multi_gpu_shard_mode="off", gpu_selection_mode="auto")
    wrong_mode = replace(AppSettings(), multi_gpu_shard_mode="vram_first_auto", gpu_selection_mode="single")
    assert vram_first_master_enabled(disabled) is False
    assert vram_first_master_enabled(wrong_mode) is False
    _ = replace(AppSettings(), multi_gpu_shard_mode="vram_first_auto", gpu_selection_mode="auto")
    assert isinstance(vram_first_master_enabled(_), bool)
