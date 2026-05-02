"""LLM-screened article relevance pass (Phase 10).

The crawler pulls long pages from open-web sources. Even after the
deterministic
[`article_clean`](article_clean.py) cleaner strips obvious wiki rails, the
text still contains site copy that derails the script LLM (about boxes,
"see also" lists, related-game paragraphs, ad / cookie residuals…).

This module asks the script LLM, **chunk by chunk**, "is this part of the
actual story?" and recomposes only the kept chunks into a tight excerpt.
Resource discipline:

* Reuses the ``llm_holder`` from
  [`src/content/llm_session.py`](llm_session.py) when the pipeline already
  loaded a model — no extra reloads.
* Hard cap on number of chunks (default 8) and character length per chunk
  (default 1800).
* Per-URL persistent cache keyed by URL + text content hash, so reruns of
  the same article skip the LLM entirely.
* Disable globally with ``AQUADUCT_ARTICLE_RELEVANCE_SCREEN=0``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.content.article_chunker import ArticleChunk, chunk_article_text
from src.content.brain import _infer_text_with_optional_holder


_LOG = logging.getLogger(__name__)

DEFAULT_TARGET_CHARS = 1800
DEFAULT_MAX_CHUNKS = 8
DEFAULT_MAX_CHARS = 8000
DEFAULT_MAX_NEW_TOKENS = 96


@dataclass
class RelevanceResult:
    excerpt: str
    kept: list[int]
    total_chunks: int
    cache_hit: bool
    used_llm: bool


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _falsy(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"0", "false", "no", "off"}


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        return default


def cache_dir() -> Path:
    """Return the on-disk cache directory for relevance-pass results."""
    try:
        from src.core.config import get_paths

        base = Path(get_paths().cache_dir)
    except Exception:
        base = Path.home() / ".cache" / "aquaduct"
    p = base / "article_relevance"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _content_hash(*, url: str, text: str, target: int, max_chunks: int) -> str:
    h = hashlib.sha256()
    h.update((url or "").encode("utf-8"))
    h.update(b"\x00")
    h.update((text or "").encode("utf-8"))
    h.update(b"\x00")
    h.update(f"t={target},n={max_chunks}".encode("utf-8"))
    return h.hexdigest()[:32]


def _read_cache(key: str) -> dict[str, Any] | None:
    p = cache_dir() / f"{key}.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("kept"), list):
            return data
    except (OSError, ValueError):
        return None
    return None


def _write_cache(key: str, payload: dict[str, Any]) -> None:
    try:
        (cache_dir() / f"{key}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


_KEEP_PAT = re.compile(r"\b(keep|relevant|story|yes)\b", re.IGNORECASE)
_DROP_PAT = re.compile(r"\b(drop|skip|irrelevant|chrome|navigation|sidebar|no)\b", re.IGNORECASE)


def _llm_classify_chunk_keep(reply: str) -> bool:
    """Map a free-form LLM reply to a binary keep/drop decision."""
    body = (reply or "").strip()
    if not body:
        return True
    head = body[:200]
    try:
        data = json.loads(head if head.startswith("{") else f'{{"x":{head}}}')
        if isinstance(data, dict):
            for k in ("keep", "relevant", "story"):
                if k in data:
                    v = data.get(k)
                    if isinstance(v, bool):
                        return v
                    if isinstance(v, str):
                        return v.strip().lower() in {"yes", "true", "1", "keep"}
    except (ValueError, TypeError):
        pass
    if _DROP_PAT.search(head) and not _KEEP_PAT.search(head):
        return False
    if _KEEP_PAT.search(head):
        return True
    return True


def _build_chunk_prompt(
    *,
    chunk: ArticleChunk,
    topic_hint: str,
    video_format: str,
) -> str:
    fmt = (video_format or "").strip().lower() or "short video"
    topic = (topic_hint or "").strip()
    topic_line = f"Topic / story angle: {topic}\n" if topic else ""
    return (
        "You are filtering web-page text to keep ONLY the actual story / article body for a "
        f"{fmt} script. Drop site chrome (navigation, ads, related links, share rails, cookie "
        "banners, 'about', 'fan feed', 'trending', 'see more'). If the chunk is genuine "
        "narrative / reportage / fiction body, keep it.\n"
        f"{topic_line}"
        "Reply with a single JSON object: {\"keep\": true} or {\"keep\": false}. "
        "Do not output any other text.\n"
        "\n"
        "<chunk>\n"
        f"{chunk.text}\n"
        "</chunk>\n"
    )


def relevance_screen_enabled(settings: Any | None) -> bool:
    """Resolve whether the relevance screen should run for this run."""
    env = os.environ.get("AQUADUCT_ARTICLE_RELEVANCE_SCREEN", "").strip()
    if _falsy(env):
        return False
    if _truthy(env):
        return True
    if settings is None:
        return True
    val = getattr(settings, "article_relevance_screen", None)
    if val is None:
        return True
    return bool(val)


def screen_article_relevance(
    text: str,
    *,
    url: str | None = None,
    topic_hint: str = "",
    video_format: str = "",
    llm_holder: MutableMapping[str, Any] | None = None,
    model_id: str | None = None,
    inference_settings: Any | None = None,
    target_chunk_chars: int | None = None,
    max_chunks: int | None = None,
    max_chars: int | None = None,
    max_new_tokens: int | None = None,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    use_cache: bool = True,
) -> RelevanceResult:
    """Run the chunked relevance pass and return a tightened excerpt.

    When the LLM holder lacks a loaded model and ``model_id`` is empty, the
    pass is skipped and the original (cleaned) text is returned unchanged.
    """
    target = int(target_chunk_chars or _env_int("AQUADUCT_ARTICLE_RELEVANCE_CHUNK_CHARS", DEFAULT_TARGET_CHARS))
    max_n = int(max_chunks or _env_int("AQUADUCT_ARTICLE_RELEVANCE_MAX_CHUNKS", DEFAULT_MAX_CHUNKS))
    cap = int(max_chars or _env_int("AQUADUCT_ARTICLE_RELEVANCE_MAX_CHARS", DEFAULT_MAX_CHARS))
    new_tok = int(max_new_tokens or _env_int("AQUADUCT_ARTICLE_RELEVANCE_NEW_TOKENS", DEFAULT_MAX_NEW_TOKENS))

    body = (text or "").strip()
    if not body:
        return RelevanceResult(excerpt="", kept=[], total_chunks=0, cache_hit=False, used_llm=False)

    chunks = chunk_article_text(body, target_chars=target, max_chunks=max_n)
    total = len(chunks)
    if total == 0:
        return RelevanceResult(excerpt="", kept=[], total_chunks=0, cache_hit=False, used_llm=False)

    if total == 1:
        excerpt = chunks[0].text
        if len(excerpt) > cap:
            excerpt = excerpt[: cap - 1] + "…"
        return RelevanceResult(
            excerpt=excerpt, kept=[0], total_chunks=1, cache_hit=False, used_llm=False
        )

    cache_key = _content_hash(url=url or "", text=body, target=target, max_chunks=max_n)
    if use_cache:
        cached = _read_cache(cache_key)
        if cached is not None:
            kept = [int(i) for i in cached.get("kept", []) if isinstance(i, int)]
            kept = [i for i in kept if 0 <= i < total]
            recomposed = "\n\n".join(chunks[i].text for i in kept) if kept else "\n\n".join(c.text for c in chunks)
            if len(recomposed) > cap:
                recomposed = recomposed[: cap - 1] + "…"
            return RelevanceResult(
                excerpt=recomposed,
                kept=kept,
                total_chunks=total,
                cache_hit=True,
                used_llm=False,
            )

    have_holder_model = bool(llm_holder is not None and llm_holder.get("model") is not None)
    if not have_holder_model and not (model_id or "").strip():
        excerpt = "\n\n".join(c.text for c in chunks)
        if len(excerpt) > cap:
            excerpt = excerpt[: cap - 1] + "…"
        return RelevanceResult(
            excerpt=excerpt, kept=list(range(total)), total_chunks=total, cache_hit=False, used_llm=False
        )

    used_model_id = (
        str(llm_holder.get("hub_model_id", "")) if llm_holder else ""
    ) or str(model_id or "")

    kept_indices: list[int] = []
    for ch in chunks:
        prompt = _build_chunk_prompt(chunk=ch, topic_hint=topic_hint, video_format=video_format)
        if on_llm_task:
            on_llm_task(
                "article_relevance",
                int(100 * (ch.index + 1) / max(1, total)),
                f"Screening chunk {ch.index + 1}/{total} ({ch.length} chars)",
            )
        try:
            reply = _infer_text_with_optional_holder(
                used_model_id,
                prompt,
                llm_holder=llm_holder,
                on_llm_task=None,
                max_new_tokens=new_tok,
                inference_settings=inference_settings,
            )
        except Exception as e:
            _LOG.debug("article_relevance: LLM call failed for chunk %d: %s", ch.index, e)
            kept_indices.append(ch.index)
            continue
        if _llm_classify_chunk_keep(reply):
            kept_indices.append(ch.index)

    if not kept_indices:
        kept_indices = list(range(total))

    if use_cache:
        _write_cache(
            cache_key,
            {
                "url": url or "",
                "kept": kept_indices,
                "total_chunks": total,
                "target_chars": target,
                "max_chunks": max_n,
                "model_id": used_model_id,
            },
        )

    excerpt = "\n\n".join(chunks[i].text for i in kept_indices)
    if len(excerpt) > cap:
        excerpt = excerpt[: cap - 1] + "…"
    return RelevanceResult(
        excerpt=excerpt,
        kept=kept_indices,
        total_chunks=total,
        cache_hit=False,
        used_llm=True,
    )
