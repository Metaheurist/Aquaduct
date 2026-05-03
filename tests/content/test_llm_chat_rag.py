from __future__ import annotations

from pathlib import Path

import numpy as np

from src.content.llm_chat_rag import (
    ChatDocsIndex,
    DocSnippet,
    _BM25Index,
    _mmr_diversity,
    _minmax,
    _save_static_cache,
    _try_load_static_cache,
    collect_docs_md_snippets,
    format_retrieval_block,
)


def test_bm25_ranks_synthetic_query() -> None:
    bm = _BM25Index(
        [
            "how to add a topic tag on the topics tab",
            "watermark settings live on branding",
            "hello world",
        ]
    )
    s = bm.scores("where is the watermark")
    assert s[1] > s[0]
    assert s[1] > s[2]


def test_minmax_single_value_is_one() -> None:
    x = np.array([2.0], dtype=np.float64)
    assert float(_minmax(x)[0]) == 1.0


def test_collect_docs_chunks(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "guide.md").write_text(
        "## Alpha\nFirst bit.\n\n### Beta\nSecond bit with more text.\n",
        encoding="utf-8",
    )
    from src.content import llm_chat_rag as rag

    monkeypatch.setattr(rag, "installation_dir", lambda: tmp_path)
    snips = collect_docs_md_snippets(docs_root=root, install=tmp_path, chunk_cap=200)
    assert any("Alpha" in s.source for s in snips)
    assert any(s.anchor.startswith("docs:docs/guide.md#") for s in snips)


def test_format_retrieval_block_budget() -> None:
    hits = [
        (DocSnippet("1", "S1", "a1", "x" * 500), 1.0),
    ]
    short = format_retrieval_block(hits, char_budget=600)
    assert "S1" in short
    assert len(short) < 800


def test_static_cache_roundtrip(tmp_path: Path, monkeypatch) -> None:
    from src.content import llm_chat_rag as rag

    monkeypatch.setattr(rag, "_cache_dir", lambda: tmp_path / "c")
    snips = [
        DocSnippet("a", "src A", "x", "hello topics tab"),
        DocSnippet("b", "src B", "y", "branding watermark"),
    ]
    emb = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    _save_static_cache("m1", "sig1", snips, emb)
    hit = _try_load_static_cache("m1", "sig1", 2)
    assert hit is not None
    out_snips, out_emb = hit
    assert len(out_snips) == 2
    assert out_emb.shape == (2, 2)


def test_mmr_prefers_diverse_groups() -> None:
    snippets = [
        DocSnippet("t:a:s1", "T", "a", "x"),
        DocSnippet("t:a:s2", "T", "a", "y"),
        DocSnippet("d:file.md#h", "D", "b", "z"),
    ]
    emb = np.eye(3, dtype=np.float32)
    idx = np.array([0, 1, 2], dtype=np.int64)
    scores = np.array([1.0, 0.95, 0.9], dtype=np.float64)
    picked = _mmr_diversity(
        idx,
        scores,
        emb,
        k=2,
        lambda_=0.7,
        group_key_fn=lambda i: ("a" if i < 2 else "b"),
    )
    assert 2 in picked


def test_hybrid_search_with_mock_embeddings() -> None:
    snippets = [
        DocSnippet("1", "Watermark doc", "docs:x#h", "watermark opacity branding"),
        DocSnippet("2", "Unrelated", "docs:y#h", "ffmpeg mux audio"),
    ]
    bm = _BM25Index([s.text for s in snippets])
    q = np.array([1.0, 0.0], dtype=np.float32)
    doc_e = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

    class Enc:
        def encode(self, texts: list[str]) -> np.ndarray:
            if texts == ["watermark help"]:
                return q.reshape(1, -1)
            return np.zeros((len(texts), 2), dtype=np.float32)

    ix = ChatDocsIndex(
        list(snippets),
        bm25=bm,
        embeddings=doc_e,
        encoder=Enc(),  # type: ignore[arg-type]
    )
    hits = ix.search("watermark help", k=2, min_score=0.01)
    assert hits and "Watermark" in hits[0][0].source
