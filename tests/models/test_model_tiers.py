from __future__ import annotations

from src.models.model_tiers import (
    TIER_LITE,
    TIER_PRO,
    TIER_STANDARD,
    api_tier_for_model,
    local_tier_for_repo,
    tier_badge,
    tier_label,
    tier_sort_rank,
)
from src.models.model_manager import model_options


def test_tier_labels() -> None:
    assert "[Pro]" in tier_badge(TIER_PRO)
    assert tier_label(TIER_STANDARD) == "Standard"


def test_tier_sort_rank_lite_standard_pro() -> None:
    assert tier_sort_rank(TIER_LITE) < tier_sort_rank(TIER_STANDARD) < tier_sort_rank(TIER_PRO)


def test_local_tier_covers_all_curated() -> None:
    repos = {o.repo_id for o in model_options()}
    for rid in repos:
        t = local_tier_for_repo(rid)
        assert t in (TIER_PRO, TIER_STANDARD, TIER_LITE)


def test_api_openai_tiers() -> None:
    assert api_tier_for_model("openai", "gpt-4o-mini") == TIER_LITE
    assert api_tier_for_model("openai", "gpt-4o") == TIER_PRO
    assert api_tier_for_model("openai", "dall-e-3") == TIER_PRO


def test_api_google_gemini_flash_vs_pro() -> None:
    assert api_tier_for_model("google_ai_studio", "gemini-2.5-flash") == TIER_STANDARD
    assert api_tier_for_model("google_ai_studio", "gemini-2.5-pro") == TIER_PRO


def test_api_kling_inworld() -> None:
    assert api_tier_for_model("kling", "kling-v3") == TIER_PRO
    assert api_tier_for_model("kling", "kling-v2-master") == TIER_PRO
    assert api_tier_for_model("inworld", "inworld-tts-1.5-mini") == TIER_LITE
