"""Hybrid BM25 + embedding retrieval for LLM chat (docs, tutorials, live tooltips).

Static corpus embeddings are cached under ``application_data_dir() / .cache / chat_rag``.
Tooltip text is collected on the GUI thread; encoding + cache IO may run on a worker thread.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Final, Sequence

import numpy as np

from debug import dprint
from src.core.app_dirs import application_data_dir, installation_dir

SCHEMA_VERSION: Final[int] = 1
DEFAULT_EMBED_MODEL_ID: Final[str] = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_CHAR_CAP: Final[int] = 600
ANN_MIN_SNIPPETS_DEFAULT: Final[int] = 5000
_STOPWORDS: Final[frozenset[str]] = frozenset(
    "the a an and or of to is in on for with as by it this that".split()
)

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _ann_min_snippets() -> int:
    try:
        return max(2, int(os.environ.get("AQUADUCT_CHAT_ANN_MIN", str(ANN_MIN_SNIPPETS_DEFAULT))))
    except ValueError:
        return ANN_MIN_SNIPPETS_DEFAULT


_cross_encoder_tok: Any = None
_cross_encoder_model: Any = None
_cross_encoder_failed: bool = False


def _cross_encoder_wanted() -> bool:
    if os.environ.get("AQUADUCT_CHAT_RERANK", "").strip() == "1":
        return True
    return bool(os.environ.get("AQUADUCT_CHAT_RERANK_MODEL", "").strip())


def _default_rerank_model_id() -> str:
    return (os.environ.get("AQUADUCT_CHAT_RERANK_MODEL") or "cross-encoder/ms-marco-MiniLM-L-6-v2").strip()


def _get_cross_encoder() -> tuple[Any, Any]:
    global _cross_encoder_tok, _cross_encoder_model, _cross_encoder_failed
    if _cross_encoder_failed:
        return None, None
    if not _cross_encoder_wanted():
        return None, None
    if _cross_encoder_model is not None:
        return _cross_encoder_tok, _cross_encoder_model
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        mid = _default_rerank_model_id()
        tok = AutoTokenizer.from_pretrained(mid, trust_remote_code=True)
        mod = AutoModelForSequenceClassification.from_pretrained(mid, trust_remote_code=True)
        mod.eval()
        mod.to("cpu")
        _cross_encoder_tok, _cross_encoder_model = tok, mod
        return tok, mod
    except Exception as e:
        _cross_encoder_failed = True
        dprint("chat_rag", "cross-encoder unavailable, MMR-only", str(e)[:300])
        return None, None


def _cross_encoder_scores(query: str, texts: list[str]) -> np.ndarray:
    tok, mod = _get_cross_encoder()
    if tok is None or mod is None or not texts:
        return np.array([], dtype=np.float64)
    import torch

    out: list[float] = []
    bs = 16
    q = (query or "").strip()
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            batch = texts[i : i + bs]
            pairs: list[list[str]] = [[q, (t or "")[:6000]] for t in batch]
            enc = tok(pairs, padding=True, truncation=True, max_length=256, return_tensors="pt")
            enc = {k: v.to(mod.device) for k, v in enc.items()}
            logits = mod(**enc).logits
            arr = logits.detach().squeeze(-1).float().cpu().numpy()
            if arr.ndim == 0:
                out.append(float(arr))
            else:
                out.extend(float(x) for x in arr.reshape(-1))
    return np.array(out, dtype=np.float64)


def _tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall((text or "").lower()) if t and t not in _STOPWORDS]


def _strip_html(html: str) -> str:
    s = re.sub(r"(?is)<script.*?>.*?</script>", "", html)
    s = re.sub(r"(?is)<style.*?>.*?</style>", "", s)
    s = re.sub(r"(?s)<.*?>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _slug_heading(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", (title or "").strip().lower()).strip("_")
    return s or "section"


def _strip_yaml_front_matter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end < 0:
        return text
    return text[end + 5 :]


def _strip_fenced_code_blocks(text: str) -> str:
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        st = line.strip()
        if st.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def _cap_body(title: str, body: str, *, max_chars: int) -> list[tuple[str, str]]:
    """Return (heading, chunk_text) pieces under max_chars."""
    header = f"## {title}\n" if title else ""
    raw = (header + body).strip()
    if len(raw) <= max_chars:
        return [(title, raw)] if raw else []
    pieces: list[tuple[str, str]] = []
    buf = header
    for part in re.split(r"(?<=[.!?])\s+", body):
        if len(buf) + len(part) + 1 <= max_chars:
            buf = f"{buf} {part}".strip() if buf else part
        else:
            if buf.strip():
                pieces.append((title, buf.strip()))
            buf = part
        if len(buf) >= max_chars:
            pieces.append((title, buf[:max_chars].strip()))
            buf = buf[max_chars:]
    if buf.strip():
        pieces.append((title, buf.strip()))
    return pieces


def _chunk_markdown_by_headings(body: str, *, max_chars: int) -> list[tuple[str, str]]:
    lines = body.splitlines()
    chunks: list[tuple[str, str]] = []
    current_title = "Overview"
    current: list[str] = []

    def flush() -> None:
        text = "\n".join(current).strip()
        if text:
            chunks.extend(_cap_body(current_title, text, max_chars=max_chars))
        current.clear()

    for line in lines:
        m = re.match(r"^(#{2,3})\s+(.+)$", line)
        if m:
            flush()
            current_title = m.group(2).strip()
        else:
            current.append(line)
    flush()
    return chunks


class _BM25Index:
    """Hand-rolled Okapi BM25 (k1=1.5, b=0.75)."""

    def __init__(self, docs: Sequence[str]) -> None:
        self._doc_tokens = [_tokenize(t) for t in docs]
        self._N = len(docs)
        self._avgdl = (
            sum(len(toks) for toks in self._doc_tokens) / max(1, self._N) if self._N else 0.0
        )
        df: dict[str, int] = {}
        for toks in self._doc_tokens:
            for w in frozenset(toks):
                df[w] = df.get(w, 0) + 1
        self._idf = {w: math.log(1.0 + (self._N - df[w] + 0.5) / (df[w] + 0.5)) for w in df}

    def scores(self, query: str) -> np.ndarray:
        q_tokens = _tokenize(query)
        if not q_tokens or not self._doc_tokens:
            return np.zeros(self._N, dtype=np.float64)
        out = np.zeros(self._N, dtype=np.float64)
        k1, b = 1.5, 0.75
        for qi in q_tokens:
            idf = self._idf.get(qi)
            if idf is None:
                continue
            for i, toks in enumerate(self._doc_tokens):
                f = sum(1 for t in toks if t == qi)
                if not f:
                    continue
                dl = len(toks)
                denom = f + k1 * (1 - b + b * dl / (self._avgdl or 1.0))
                out[i] += idf * (f * (k1 + 1)) / denom
        return out


@dataclass(frozen=True)
class DocSnippet:
    doc_id: str
    source: str
    anchor: str
    text: str

    def to_json(self) -> dict[str, str]:
        return {"doc_id": self.doc_id, "source": self.source, "anchor": self.anchor, "text": self.text}

    @staticmethod
    def from_json(d: dict[str, Any]) -> DocSnippet:
        return DocSnippet(
            doc_id=str(d["doc_id"]),
            source=str(d["source"]),
            anchor=str(d["anchor"]),
            text=str(d["text"]),
        )


def collect_docs_md_snippets(
    *,
    docs_root: Path | None = None,
    install: Path | None = None,
    chunk_cap: int = CHUNK_CHAR_CAP,
) -> list[DocSnippet]:
    root = docs_root or (installation_dir() / "docs")
    if not root.is_dir():
        return []
    base = install or installation_dir()
    out: list[DocSnippet] = []
    try:
        paths = sorted(root.rglob("*.md"))
    except OSError:
        return []
    for path in paths:
        try:
            rel = path.relative_to(base).as_posix()
        except ValueError:
            rel = path.name
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body = _strip_fenced_code_blocks(_strip_yaml_front_matter(raw))
        for heading, chunk in _chunk_markdown_by_headings(body, max_chars=chunk_cap):
            sl = _slug_heading(heading)
            doc_id = f"d:{rel}#{sl}"
            source = f"Docs - {rel} - {heading}"
            anchor = f"docs:{rel}#{sl}"
            out.append(DocSnippet(doc_id=doc_id, source=source, anchor=anchor, text=chunk[:8000]))
    return out


def collect_tutorial_snippets(*, chunk_cap: int = CHUNK_CHAR_CAP) -> list[DocSnippet]:
    from UI.dialogs.tutorial_dialog import TUTORIAL_TOPICS

    out: list[DocSnippet] = []
    for topic in TUTORIAL_TOPICS:
        for n, (slide_title, body) in enumerate(topic.slides, start=1):
            plain = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)
            chunks = _cap_body(slide_title, plain.strip(), max_chars=chunk_cap)
            for part_i, (_, chunk) in enumerate(chunks):
                sid = f"t:{topic.topic_id}:s{n}" + (f":p{part_i}" if len(chunks) > 1 else "")
                source = f"Tutorial - {topic.label} - Slide {n}: {slide_title}"
                anchor = f"{topic.topic_id}#slide={n}"
                out.append(
                    DocSnippet(
                        doc_id=sid,
                        source=source,
                        anchor=anchor,
                        text=chunk[:8000],
                    )
                )
    return out


def collect_static_snippets() -> list[DocSnippet]:
    return collect_docs_md_snippets() + collect_tutorial_snippets()


def collect_tooltip_snippets(win: Any) -> list[DocSnippet]:
    from PyQt6.QtWidgets import QWidget

    widgets: list = win.findChildren(QWidget)
    out: list[DocSnippet] = []
    seen: set[tuple[str, str]] = set()
    for i, w in enumerate(widgets):
        try:
            tip = str(w.toolTip() or "").strip()
        except Exception:
            continue
        if not tip or tip.startswith("about:blank"):
            continue
        plain = _strip_html(tip)
        if len(plain) < 8:
            continue
        oid = str(w.objectName() or "").strip()
        acc = str(w.accessibleName() or "").strip()
        label = acc or oid or f"widget_{i}"
        key = (plain[:240], oid)
        if key in seen:
            continue
        seen.add(key)
        doc_id = f"w:{oid or label}:{i}"
        source = f"Tooltip - {label}"
        anchor = oid or f"ui:{i}"
        out.append(
            DocSnippet(
                doc_id=doc_id,
                source=source,
                anchor=anchor,
                text=plain[:800],
            )
        )
    return out


def static_corpus_signature() -> str:
    """Hash docs tree + tutorial source files (not live tooltips)."""
    h = hashlib.sha256()
    install = installation_dir()
    docs = install / "docs"
    if docs.is_dir():
        try:
            paths = sorted(docs.rglob("*.md"))
        except OSError:
            paths = []
        for path in paths:
            try:
                rel = path.relative_to(install).as_posix()
            except ValueError:
                rel = str(path)
            try:
                st = path.stat()
            except OSError:
                continue
            h.update(rel.encode("utf-8", errors="replace"))
            h.update(b"\0")
            h.update(str(st.st_mtime_ns).encode("ascii"))
            h.update(b"\0")
            h.update(str(st.st_size).encode("ascii"))
            h.update(b"\n")
    for name in ("UI/dialogs/tutorial_dialog.py", "UI/help/tutorial_links.py"):
        path = install / name
        if path.is_file():
            try:
                st = path.stat()
                h.update(name.encode())
                h.update(str(st.st_mtime_ns).encode("ascii"))
                h.update(str(st.st_size).encode("ascii"))
                h.update(b"\n")
            except OSError:
                pass
    return h.hexdigest()


def _embed_model_id() -> str:
    return (os.environ.get("AQUADUCT_CHAT_EMBED_MODEL") or DEFAULT_EMBED_MODEL_ID).strip()


def _model_slug(model_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", model_id)[:120] or "embed"


def _cache_dir() -> Path:
    return application_data_dir() / ".cache" / "chat_rag"


def _try_import_hnsw() -> Any | None:
    try:
        import hnswlib

        return hnswlib
    except Exception:
        return None


def _save_static_hnsw(model_id: str, emb: np.ndarray) -> None:
    hlib = _try_import_hnsw()
    if hlib is None or emb.size == 0:
        return
    n, d = emb.shape
    if n < _ann_min_snippets():
        return
    cache = _cache_dir() / _model_slug(model_id)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "static_hnsw.bin"
    idx = hlib.Index(space="ip", dim=int(d))
    max_el = max(int(n) + 8192, int(n) + 1)
    idx.init_index(max_elements=max_el, ef_construction=200, M=16)
    idx.add_items(np.asarray(emb, dtype=np.float32), np.arange(n, dtype=np.int64))
    idx.save_index(str(path))


def _try_load_static_hnsw(model_id: str, *, dim: int, static_n: int) -> Any | None:
    hlib = _try_import_hnsw()
    if hlib is None:
        return None
    path = _cache_dir() / _model_slug(model_id) / "static_hnsw.bin"
    if not path.is_file():
        return None
    try:
        idx = hlib.Index(space="ip", dim=int(dim))
        idx.load_index(str(path), max_elements=max(int(static_n) + 8192, int(static_n) + 1))
        cur = int(idx.get_current_count())
        if cur != int(static_n):
            return None
        return idx
    except Exception:
        return None


class _TextEncoder:
    """Mean-pooled, L2-normalized sentence embeddings via Transformers (CPU)."""

    def __init__(self, model_id: str) -> None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        self._model = AutoModel.from_pretrained(model_id, trust_remote_code=True)
        self._model.eval()
        self._model.to("cpu")
        self.dim: int | None = None
        with torch.no_grad():
            probe = self._encode_batch(["probe"], batch_size=1)
        self.dim = int(probe.shape[1]) if probe.size else None

    def _encode_batch(self, texts: list[str], *, batch_size: int = 32) -> np.ndarray:
        import torch

        outs: list[np.ndarray] = []
        self._model.eval()
        with torch.no_grad():
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                toks = self._tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                )
                toks = {k: v.to(self._model.device) for k, v in toks.items()}
                out = self._model(**toks)
                last = out.last_hidden_state
                mask = toks["attention_mask"].unsqueeze(-1).expand(last.size()).float()
                summed = torch.sum(last * mask, dim=1)
                counts = torch.clamp(mask.sum(dim=1), min=1e-9)
                mean = summed / counts
                mean = torch.nn.functional.normalize(mean, p=2, dim=1)
                outs.append(mean.cpu().numpy().astype(np.float32))
        if not outs:
            return np.zeros((0, int(self.dim or 0)), dtype=np.float32)
        return np.vstack(outs)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        tlist = [str(t or "")[:8000] for t in texts]
        if not tlist:
            return np.zeros((0, int(self.dim or 384)), dtype=np.float32)
        return self._encode_batch(tlist)


def try_make_text_encoder(model_id: str | None = None) -> _TextEncoder | None:
    mid = model_id or _embed_model_id()
    try:
        return _TextEncoder(mid)
    except Exception as e:
        dprint("chat_rag", "embed_model unavailable, BM25-only", str(e)[:300])
        return None


def _try_load_static_cache(
    model_id: str,
    signature: str,
    snippet_count: int,
) -> tuple[list[DocSnippet], np.ndarray] | None:
    cache = _cache_dir() / _model_slug(model_id)
    mf = cache / "manifest.json"
    if not mf.is_file():
        return None
    try:
        manifest = json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(manifest.get("schema_version", 0)) != SCHEMA_VERSION:
        return None
    if str(manifest.get("embed_model_id")) != model_id:
        return None
    if str(manifest.get("corpus_signature")) != signature:
        return None
    if int(manifest.get("static_snippet_count", -1)) != snippet_count:
        return None
    jf = cache / "static_snippets.json"
    nz = cache / "static_embeddings.npz"
    if not jf.is_file() or not nz.is_file():
        return None
    try:
        raw_list = json.loads(jf.read_text(encoding="utf-8"))
        rows = np.load(nz)
        emb = np.asarray(rows["embeddings"], dtype=np.float32)
        if emb.ndim != 2 or emb.shape[0] != len(raw_list):
            return None
        snippets = [DocSnippet.from_json(x) for x in raw_list]
        if len(snippets) != emb.shape[0]:
            return None
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        norms = np.where(norms < 1e-9, 1.0, norms)
        emb = emb / norms
        return snippets, emb
    except Exception:
        return None


def _save_static_cache(
    model_id: str,
    signature: str,
    static_snippets: list[DocSnippet],
    embeddings: np.ndarray,
) -> None:
    cache = _cache_dir() / _model_slug(model_id)
    cache.mkdir(parents=True, exist_ok=True)
    jdat = [s.to_json() for s in static_snippets]
    emb_dim = int(embeddings.shape[1]) if embeddings.ndim == 2 else 0
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "embed_model_id": model_id,
        "embed_dim": emb_dim,
        "corpus_signature": signature,
        "static_snippet_count": len(static_snippets),
    }
    tmp_dir = cache
    snippets_path = tmp_dir / "static_snippets.json.tmp"
    emb_pack = tmp_dir / "static_embeddings_pack"
    manifest_path = tmp_dir / "manifest.json.tmp"
    snippets_path.write_text(json.dumps(jdat, ensure_ascii=False) + "\n", encoding="utf-8")
    np.savez_compressed(emb_pack, embeddings=np.asarray(embeddings, dtype=np.float32))
    written_npz = emb_pack.with_suffix(".npz")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    snippets_path.replace(tmp_dir / "static_snippets.json")
    written_npz.replace(tmp_dir / "static_embeddings.npz")
    manifest_path.replace(tmp_dir / "manifest.json")


def _encode_static_with_cache(
    model_id: str,
    signature: str,
    static_snippets: list[DocSnippet],
    encoder: _TextEncoder,
) -> np.ndarray:
    hit = _try_load_static_cache(model_id, signature, len(static_snippets))
    if hit is not None:
        cached_snips, emb = hit
        if [s.doc_id for s in cached_snips] == [s.doc_id for s in static_snippets]:
            dprint("chat_rag", "loaded static embedding cache", f"n={len(static_snippets)}")
            return emb
    texts = [s.text for s in static_snippets]
    emb = encoder.encode(texts)
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms = np.where(norms < 1e-9, 1.0, norms)
    emb = emb / norms
    try:
        _save_static_cache(model_id, signature, static_snippets, emb)
        dprint("chat_rag", "saved static embedding cache", f"n={len(static_snippets)}")
        if len(static_snippets) >= _ann_min_snippets():
            try:
                _save_static_hnsw(model_id, emb)
            except Exception as e:
                dprint("chat_rag", "hnsw static save failed", str(e)[:120])
    except Exception as e:
        dprint("chat_rag", "cache save failed", str(e)[:200])
    return emb


def _minmax(x: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x
    lo, hi = float(np.min(x)), float(np.max(x))
    if hi - lo < 1e-12:
        return np.ones_like(x, dtype=np.float64)
    return ((x - lo) / (hi - lo)).astype(np.float64)


def _mmr_diversity(
    cand_idx: np.ndarray,
    cand_score: np.ndarray,
    embeddings: np.ndarray,
    *,
    k: int,
    lambda_: float,
    group_key_fn: Callable[[int], str],
) -> list[int]:
    """Maximal marginal relevance on candidate indices (by embedding similarity)."""
    if cand_idx.size == 0 or k <= 0:
        return []
    selected: list[int] = []
    candidates = list(cand_idx)
    scores = {int(i): float(cand_score[j]) for j, i in enumerate(cand_idx)}
    key_sel: set[str] = set()

    def sim_rows(a: int, b: int) -> float:
        va, vb = embeddings[a], embeddings[b]
        return float(np.dot(va, vb))

    while candidates and len(selected) < k:
        best_i = -1
        best_val = -1e9
        for i in candidates:
            g = group_key_fn(i)
            # Penalize if we already picked from same group (tab/topic/file)
            bonus = 0.0 if g not in key_sel else -0.35
            div = 0.0
            if selected:
                div = max(sim_rows(i, s) for s in selected)
            mmr = lambda_ * scores[i] + bonus - (1.0 - lambda_) * div
            if mmr > best_val:
                best_val = mmr
                best_i = i
        if best_i < 0:
            break
        selected.append(best_i)
        candidates.remove(best_i)
        key_sel.add(group_key_fn(best_i))
    return selected


def _group_key_for_snippet(snippets: Sequence[DocSnippet], idx: int) -> str:
    s = snippets[idx]
    if s.anchor.startswith("docs:"):
        base = s.anchor.split("#", 1)[0]
        return base
    if s.doc_id.startswith("t:"):
        part = s.doc_id.split(":", 2)
        return part[1] if len(part) > 1 else s.doc_id
    return s.doc_id.split(":", 1)[0] if ":" in s.doc_id else s.doc_id


class ChatDocsIndex:
    def __init__(
        self,
        snippets: list[DocSnippet],
        *,
        bm25: _BM25Index,
        embeddings: np.ndarray | None,
        encoder: _TextEncoder | None,
        embed_model_id: str | None = None,
        hnsw_index: Any | None = None,
    ) -> None:
        self._snippets = snippets
        self._bm25 = bm25
        self._embeddings = embeddings
        self._encoder = encoder
        self._embed_model_id = embed_model_id
        self._hnsw_index = hnsw_index

    @property
    def snippets(self) -> list[DocSnippet]:
        return self._snippets

    def search(
        self,
        query: str,
        *,
        k: int = 3,
        min_score: float = 0.5,
        top_n: int = 20,
        fuse_alpha: float = 0.4,
        mmr_lambda: float = 0.7,
    ) -> list[tuple[DocSnippet, float]]:
        q = (query or "").strip()
        if not q or not self._snippets:
            return []
        bm_scores = self._bm25.scores(q)
        cand: dict[int, float] = {}
        if bm_scores.size:
            top_idx = np.argsort(bm_scores)[::-1][:top_n]
            top_bm = bm_scores[top_idx]
            n_bm = _minmax(top_bm)
            for j, i in enumerate(top_idx):
                if bm_scores[i] > 0:
                    cand[int(i)] = float(fuse_alpha * float(n_bm[j]))
        if self._embeddings is not None and self._encoder is not None and self._embeddings.shape[0] == len(
            self._snippets
        ):
            qv = self._encoder.encode([q])
            if qv.size:
                qv = qv[0]
                qn = np.linalg.norm(qv)
                if qn > 1e-9:
                    qv = qv / qn
                if self._hnsw_index is not None:
                    kq = min(top_n, len(self._snippets))
                    lab, dist = self._hnsw_index.knn_query(
                        np.asarray(qv, dtype=np.float32).reshape(1, -1), k=kq
                    )
                    top_idx = lab[0]
                    ip = -dist[0]
                    n_cos_scores = _minmax(ip.astype(np.float64))
                    for j, i in enumerate(top_idx):
                        ii = int(i)
                        add = (1.0 - fuse_alpha) * float(n_cos_scores[j])
                        cand[ii] = cand.get(ii, 0.0) + add
                else:
                    cos = self._embeddings @ qv
                    top_idx = np.argsort(cos)[::-1][:top_n]
                    top_cos = cos[top_idx]
                    n_cos_scores = _minmax(top_cos.astype(np.float64))
                    for j, i in enumerate(top_idx):
                        ii = int(i)
                        add = (1.0 - fuse_alpha) * float(n_cos_scores[j])
                        cand[ii] = cand.get(ii, 0.0) + add
        if not cand:
            return []
        if _cross_encoder_wanted():
            rerank_n = 12
            ranked = sorted(cand.keys(), key=lambda i: cand[i], reverse=True)[: min(rerank_n, len(cand))]
            texts_r = [self._snippets[int(i)].text for i in ranked]
            ce_scores = _cross_encoder_scores(q, texts_r)
            if ce_scores.size == len(ranked):
                nrm = _minmax(ce_scores)
                for j, i in enumerate(ranked):
                    cand[int(i)] = float(nrm[j])
        idx_arr = np.array(sorted(cand.keys()), dtype=np.int64)
        raw = np.array([cand[int(i)] for i in idx_arr], dtype=np.float64)
        fused = _minmax(raw)
        order = np.argsort(fused)[::-1]
        idx_sorted = idx_arr[order]
        scores_sorted = fused[order]
        # min_score on normalized fused [0,1]
        keep = scores_sorted >= min_score
        idx_sorted = idx_sorted[keep]
        scores_sorted = scores_sorted[keep]
        if idx_sorted.size == 0:
            return []
        if self._embeddings is not None and idx_sorted.size > 1:
            picked = _mmr_diversity(
                idx_sorted,
                scores_sorted,
                self._embeddings,
                k=k,
                lambda_=mmr_lambda,
                group_key_fn=lambda ii: _group_key_for_snippet(self._snippets, ii),
            )
        else:
            picked = [int(x) for x in idx_sorted[:k]]
        out: list[tuple[DocSnippet, float]] = []
        for pi in picked[:k]:
            si = int(pi)
            # recover un-normalized fused score for ordering transparency
            sc = float(cand.get(si, 0.0))
            out.append((self._snippets[si], sc))
        return out


def build_chat_docs_index(
    static_snippets: list[DocSnippet],
    tooltip_snippets: list[DocSnippet],
    *,
    encoder: _TextEncoder | None = None,
) -> ChatDocsIndex:
    model_id = _embed_model_id()
    enc = encoder or try_make_text_encoder(model_id)
    sig = static_corpus_signature()
    static_emb: np.ndarray | None = None
    if enc is not None and static_snippets:
        static_emb = _encode_static_with_cache(model_id, sig, static_snippets, enc)
    tip_emb: np.ndarray | None = None
    if enc is not None and tooltip_snippets:
        tip_emb = enc.encode([s.text for s in tooltip_snippets])
        tip_norm = np.linalg.norm(tip_emb, axis=1, keepdims=True)
        tip_norm = np.where(tip_norm < 1e-9, 1.0, tip_norm)
        tip_emb = tip_emb / tip_norm
    combined = list(static_snippets) + list(tooltip_snippets)
    emb_full: np.ndarray | None = None
    if static_emb is not None and tip_emb is not None:
        emb_full = np.vstack([static_emb, tip_emb])
    elif static_emb is not None and not tooltip_snippets:
        emb_full = static_emb
    elif tip_emb is not None and not static_snippets:
        emb_full = tip_emb
    elif static_emb is not None:
        emb_full = static_emb
    elif tip_emb is not None:
        emb_full = tip_emb
    if emb_full is not None and emb_full.shape[0] != len(combined):
        emb_full = None
        dprint("chat_rag", "embedding row mismatch, BM25-only")
    texts = [s.text for s in combined]
    bm = _BM25Index(texts)
    use_enc = enc if emb_full is not None else None
    hnsw_index: Any | None = None
    ann_n = _ann_min_snippets()
    if emb_full is not None and len(combined) >= ann_n:
        hlib = _try_import_hnsw()
        if hlib is None:
            dprint("chat_rag", "hnswlib import failed; brute-force cosine")
        else:
            S, T = len(static_snippets), len(tooltip_snippets)
            D = int(emb_full.shape[1])
            ntot = len(combined)
            loaded = False
            if S >= ann_n and T > 0 and tip_emb is not None:
                base = _try_load_static_hnsw(model_id, dim=D, static_n=S)
                if base is not None:
                    try:
                        need = S + T
                        max_el = int(getattr(base, "max_elements", 0) or 0)
                        if max_el < need and hasattr(base, "resize_index"):
                            base.resize_index(need + 128)
                        base.add_items(np.asarray(tip_emb, dtype=np.float32), np.arange(S, S + T, dtype=np.int64))
                        base.set_ef(64)
                        hnsw_index = base
                        loaded = True
                    except Exception:
                        loaded = False
            elif S >= ann_n and T == 0:
                base = _try_load_static_hnsw(model_id, dim=D, static_n=S)
                if base is not None:
                    base.set_ef(64)
                    hnsw_index = base
                    loaded = True
            if not loaded:
                try:
                    idx = hlib.Index(space="ip", dim=D)
                    idx.init_index(max_elements=max(ntot + 128, ntot), ef_construction=200, M=16)
                    idx.add_items(np.asarray(emb_full, dtype=np.float32), np.arange(ntot, dtype=np.int64))
                    idx.set_ef(64)
                    hnsw_index = idx
                except Exception as e:
                    dprint("chat_rag", "hnsw build failed", str(e)[:120])
                    hnsw_index = None
    return ChatDocsIndex(
        combined,
        bm25=bm,
        embeddings=emb_full,
        encoder=use_enc,
        embed_model_id=model_id if use_enc else None,
        hnsw_index=hnsw_index,
    )


def index_from_main_window(win: Any) -> ChatDocsIndex:
    """Build index in-process (tooltips require GUI thread)."""
    static = collect_static_snippets()
    tips = collect_tooltip_snippets(win)
    return build_chat_docs_index(static, tips)


def format_retrieval_block(
    hits: Sequence[tuple[DocSnippet, float]],
    *,
    char_budget: int,
) -> str:
    if not hits or char_budget < 80:
        return ""
    lines: list[str] = ["Documentation excerpts (from Aquaduct help):"]
    used = len(lines[0]) + 1
    for i, (sn, _sc) in enumerate(hits, start=1):
        remain = max(0, char_budget - used - 80)
        if remain < 40:
            break
        snippet = sn.text.strip().replace("\n", " ")
        if len(snippet) > remain:
            snippet = snippet[: max(0, remain - 1)] + "..."
        line = f'{i}. ({sn.source}) {snippet}'
        lines.append(line)
        used += len(line) + 1
    lines.append("Cite the source label in your reply when relevant. If a fact is not in these excerpts, say so.")
    return "\n".join(lines)
