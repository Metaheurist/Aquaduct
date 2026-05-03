from __future__ import annotations

import numpy as np
import pytest

from src.content.llm_chat_rag import ChatDocsIndex, DocSnippet, _BM25Index


@pytest.mark.usefixtures("monkeypatch")
def test_hnsw_knn_matches_bruteforce_topk(monkeypatch) -> None:
    pytest.importorskip("hnswlib")
    import hnswlib

    monkeypatch.setenv("AQUADUCT_CHAT_ANN_MIN", "2")
    snippets = [
        DocSnippet("0", "S0", "a", "apple pie recipe"),
        DocSnippet("1", "S1", "b", "banana bread"),
        DocSnippet("2", "S2", "c", "car engine repair"),
        DocSnippet("3", "S3", "d", "dog training"),
    ]
    emb = np.random.default_rng(0).normal(size=(4, 8)).astype(np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True).clip(min=1e-9)
    bm = _BM25Index([s.text for s in snippets])
    q = emb[2].copy()

    class Enc:
        def encode(self, texts: list[str]) -> np.ndarray:
            if texts == ["banana dessert"]:
                return q.reshape(1, -1)
            return np.zeros((len(texts), 8), dtype=np.float32)

    idx = hnswlib.Index(space="ip", dim=8)
    idx.init_index(16)
    idx.add_items(emb, np.arange(4, dtype=np.int64))
    idx.set_ef(32)

    ix_h = ChatDocsIndex(
        list(snippets),
        bm25=bm,
        embeddings=emb,
        encoder=Enc(),  # type: ignore[arg-type]
        hnsw_index=idx,
    )
    ix_b = ChatDocsIndex(
        list(snippets),
        bm25=bm,
        embeddings=emb,
        encoder=Enc(),  # type: ignore[arg-type]
        hnsw_index=None,
    )
    h1 = ix_h.search("banana dessert", k=2, min_score=0.01, top_n=8)
    h2 = ix_b.search("banana dessert", k=2, min_score=0.01, top_n=8)
    assert [x[0].doc_id for x in h1] == [x[0].doc_id for x in h2]


def test_cross_encoder_rerank_swaps_order(monkeypatch) -> None:
    from src.content import llm_chat_rag as rag

    monkeypatch.setattr(rag, "_cross_encoder_failed", False)
    monkeypatch.setattr(rag, "_cross_encoder_tok", None)
    monkeypatch.setattr(rag, "_cross_encoder_model", None)
    monkeypatch.setattr(rag, "_cross_encoder_wanted", lambda: True)

    seen: list[str] = []

    def fake_ce(q: str, texts: list[str]) -> np.ndarray:
        seen.append(q)
        if len(texts) == 2:
            return np.array([0.1, 0.9], dtype=np.float64)
        return np.array([], dtype=np.float64)

    monkeypatch.setattr(rag, "_cross_encoder_scores", fake_ce)

    snippets = [
        DocSnippet("0", "A", "a", "foo foo foo foo extra"),
        DocSnippet("1", "B", "b", "foo bar miscellaneous"),
    ]
    bm = _BM25Index([s.text for s in snippets])
    # BM25-only fusion so doc0 ranks first on query "foo"; cross-encoder prefers doc1.
    ix = ChatDocsIndex(
        list(snippets),
        bm25=bm,
        embeddings=None,
        encoder=None,
    )
    hits = ix.search("foo", k=1, min_score=0.01, top_n=8)
    assert hits[0][0].doc_id == "1"
    assert seen
