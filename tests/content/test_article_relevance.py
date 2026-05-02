"""Phase 10: chunked LLM relevance pass — caching, fallbacks, and recompose."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.content.article_relevance as ar


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch, tmp_path: Path):
    """Redirect the article-relevance cache directory to a per-test tmp dir."""
    cache = tmp_path / "rel_cache"
    cache.mkdir()
    monkeypatch.setattr(ar, "cache_dir", lambda: cache)
    return cache


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Don't let host env values leak into individual tests."""
    for k in (
        "AQUADUCT_ARTICLE_RELEVANCE_SCREEN",
        "AQUADUCT_ARTICLE_RELEVANCE_CHUNK_CHARS",
        "AQUADUCT_ARTICLE_RELEVANCE_MAX_CHUNKS",
        "AQUADUCT_ARTICLE_RELEVANCE_MAX_CHARS",
        "AQUADUCT_ARTICLE_RELEVANCE_NEW_TOKENS",
    ):
        monkeypatch.delenv(k, raising=False)


def test_relevance_screen_enabled_default_true_when_no_setting() -> None:
    assert ar.relevance_screen_enabled(None) is True


def test_relevance_screen_env_off_overrides_setting(monkeypatch) -> None:
    class _S:
        article_relevance_screen = True

    monkeypatch.setenv("AQUADUCT_ARTICLE_RELEVANCE_SCREEN", "0")
    assert ar.relevance_screen_enabled(_S()) is False


def test_relevance_screen_env_on_overrides_setting_off(monkeypatch) -> None:
    class _S:
        article_relevance_screen = False

    monkeypatch.setenv("AQUADUCT_ARTICLE_RELEVANCE_SCREEN", "1")
    assert ar.relevance_screen_enabled(_S()) is True


def test_short_text_returns_single_chunk_no_llm_call(monkeypatch) -> None:
    """When the body fits in one chunk, the LLM is never called."""
    calls: list[str] = []

    def _fail(*a, **k):
        calls.append("called")
        raise AssertionError("LLM should not be invoked for single-chunk inputs")

    monkeypatch.setattr(ar, "_infer_text_with_optional_holder", _fail, raising=False)
    res = ar.screen_article_relevance("A small story body.", url="https://example.com/x")
    assert res.used_llm is False
    assert res.total_chunks == 1
    assert res.excerpt == "A small story body."
    assert calls == []


def test_skips_llm_when_no_holder_or_model_id() -> None:
    text = ("Para A. " * 50) + ("\n\nPara B. " * 50)
    res = ar.screen_article_relevance(text, url="https://example.com/x", target_chunk_chars=200, max_chunks=4)
    assert res.used_llm is False
    assert res.kept == list(range(res.total_chunks))


def test_drops_chunks_that_llm_marks_irrelevant(monkeypatch) -> None:
    text = (
        ("This is the actual horror story body. " * 30)
        + "\n\n"
        + ("Fan feed trending pages and related links. " * 30)
        + "\n\n"
        + ("Subscribe! Cookie consent footer rails. " * 30)
    )

    replies = {
        0: '{"keep": true}',
        1: '{"keep": false}',
        2: '{"keep": false}',
    }
    seen: list[int] = []

    def _fake_llm(model_id, prompt, **kwargs):
        idx = len(seen)
        seen.append(idx)
        return replies.get(idx, '{"keep": true}')

    monkeypatch.setattr(ar, "_infer_text_with_optional_holder", _fake_llm, raising=False)
    res = ar.screen_article_relevance(
        text,
        url="https://example.com/horror",
        target_chunk_chars=400,
        max_chunks=3,
        llm_holder={"model": object(), "tokenizer": object(), "hub_model_id": "fake/llm"},
    )
    assert res.used_llm is True
    assert res.kept == [0]
    assert "Fan feed" not in res.excerpt
    assert "horror story body" in res.excerpt


def test_writes_and_reuses_cache(monkeypatch) -> None:
    text = ("Body alpha. " * 60) + "\n\n" + ("Body beta. " * 60)
    calls = {"n": 0}

    def _fake_llm(model_id, prompt, **kwargs):
        calls["n"] += 1
        return '{"keep": true}'

    monkeypatch.setattr(ar, "_infer_text_with_optional_holder", _fake_llm, raising=False)
    holder = {"model": object(), "tokenizer": object(), "hub_model_id": "fake/llm"}
    first = ar.screen_article_relevance(
        text,
        url="https://example.com/cache",
        target_chunk_chars=300,
        max_chunks=4,
        llm_holder=holder,
    )
    second = ar.screen_article_relevance(
        text,
        url="https://example.com/cache",
        target_chunk_chars=300,
        max_chunks=4,
        llm_holder=holder,
    )
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.kept == first.kept
    assert calls["n"] == first.total_chunks


def test_fallback_keeps_all_when_llm_drops_everything(monkeypatch) -> None:
    """Defensive: if the LLM rejects every chunk, we keep all rather than emit empty."""
    text = ("Story body. " * 60) + "\n\n" + ("More body. " * 60)
    monkeypatch.setattr(
        ar,
        "_infer_text_with_optional_holder",
        lambda *a, **k: '{"keep": false}',
        raising=False,
    )
    res = ar.screen_article_relevance(
        text,
        url="https://example.com/q",
        target_chunk_chars=300,
        max_chunks=4,
        llm_holder={"model": object(), "tokenizer": object(), "hub_model_id": "fake/llm"},
    )
    assert res.kept == list(range(res.total_chunks))


def test_classifier_handles_freeform_replies() -> None:
    """The reply parser is forgiving: maps prose to a binary keep/drop decision."""
    assert ar._llm_classify_chunk_keep("This is the actual story; keep.") is True
    assert ar._llm_classify_chunk_keep("Drop, this is sidebar chrome.") is False
    assert ar._llm_classify_chunk_keep('{"keep": false, "why": "sidebar"}') is False
    assert ar._llm_classify_chunk_keep('{"keep": true}') is True
    assert ar._llm_classify_chunk_keep("") is True  # default: keep


def test_max_chars_trims_recomposed_excerpt(monkeypatch) -> None:
    monkeypatch.setattr(
        ar, "_infer_text_with_optional_holder", lambda *a, **k: '{"keep": true}', raising=False
    )
    text = "Sentence body. " * 1000
    res = ar.screen_article_relevance(
        text,
        url="https://example.com/y",
        target_chunk_chars=500,
        max_chunks=8,
        max_chars=400,
        llm_holder={"model": object(), "tokenizer": object(), "hub_model_id": "fake/llm"},
    )
    assert len(res.excerpt) <= 410
    assert res.excerpt.endswith("…")


def test_cache_payload_contains_kept_indices(_isolate_cache, monkeypatch) -> None:
    monkeypatch.setattr(
        ar, "_infer_text_with_optional_holder", lambda *a, **k: '{"keep": true}', raising=False
    )
    text = "Body sentence. " * 300
    ar.screen_article_relevance(
        text,
        url="https://example.com/z",
        target_chunk_chars=400,
        max_chunks=4,
        llm_holder={"model": object(), "tokenizer": object(), "hub_model_id": "fake/llm"},
    )
    files = list(_isolate_cache.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert "kept" in payload
    assert payload["url"] == "https://example.com/z"
    assert payload["model_id"] == "fake/llm"
