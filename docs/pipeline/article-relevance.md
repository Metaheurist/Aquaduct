# Article relevance pass (Phase 10)

The crawler returns long page bodies even after the deterministic
[`article_clean`](../../src/content/article_clean.py) cleaner runs. To stop
sidebar copy / "see also" rails / comment threads / cookie residuals from
leaking into the script LLM prompt, Aquaduct now runs an optional
**chunked LLM relevance pass** over each fetched article.

## Modules

* [`src/content/article_chunker.py`](../../src/content/article_chunker.py) —
  sentence-aware chunking. Splits at `. ! ?` boundaries, then paragraph
  breaks, then a hard cut. Defaults: `target_chars=1800`, `max_chunks=8`,
  `min_chars=100`.
* [`src/content/article_relevance.py`](../../src/content/article_relevance.py)
  — runs the per-chunk classification (`{"keep": true|false}`) using the
  shared LLM holder, recomposes kept chunks, and persists a per-URL cache.

## Pipeline integration

[`main.py`](../../main.py) calls `screen_article_relevance(...)` immediately
after `fetch_article_text(...)` returns and `llm_sess` is created (non-API
runs only). The screen reuses the same holder that the rest of the script
LLM stages will use, so we do not pay a second model load. After the screen
runs:

* `article_text` is replaced with the recomposed excerpt.
* `assets/article.txt` is rewritten with the screened excerpt.
* `assets/article.relevance.json` records `kept`, `total_chunks`,
  `cache_hit`, `used_llm`, and `url` for debugging / auditing.

## Resource discipline

* Hard caps on per-chunk size and chunk count (defaults `1800` chars and
  `8` chunks).
* Per-chunk `max_new_tokens=96` so the LLM only generates the
  `{"keep": ...}` JSON envelope.
* When the LLM rejects every chunk, we keep all of them — the relevance
  pass cannot return an empty excerpt.
* Per-URL cache under
  [`get_paths().cache_dir`](../../src/core/config.py)`/article_relevance/<hash>.json`,
  keyed by URL + content hash + chunker settings, so reruns of the same
  article skip the LLM entirely.

## Settings

| Knob | Where | Default | Notes |
|------|-------|---------|-------|
| `AppSettings.video.article_relevance_screen` | [`src/core/config.py`](../../src/core/config.py) | `True` | Turn the screen off per-run from settings. |
| `AQUADUCT_ARTICLE_RELEVANCE_SCREEN` | env | unset | `0`/`off` disables; `1`/`on` force-enables (overrides setting). |
| `AQUADUCT_ARTICLE_RELEVANCE_CHUNK_CHARS` | env | `1800` | Target characters per chunk. |
| `AQUADUCT_ARTICLE_RELEVANCE_MAX_CHUNKS` | env | `8` | Hard cap on chunks (and LLM calls per article). |
| `AQUADUCT_ARTICLE_RELEVANCE_MAX_CHARS` | env | `8000` | Hard cap on the final recomposed excerpt. |
| `AQUADUCT_ARTICLE_RELEVANCE_NEW_TOKENS` | env | `96` | `max_new_tokens` for the per-chunk reply. |

## Tests

* [`tests/content/test_article_chunker.py`](../../tests/content/test_article_chunker.py)
* [`tests/content/test_article_relevance.py`](../../tests/content/test_article_relevance.py)

## Order of operations (HTML → tight excerpt)

1. `crawler.fetch_article_text(url)` returns the longest text candidate.
2. `crawler.fetch_article_text(..., sanitize=True)` (default) runs
   `article_clean.clean_article_excerpt` to strip Fandom / wiki rails,
   citations, share / cookie chrome, numbered link rails (Phase 3).
3. `main.py` (Phase 10) hands the cleaned text + URL + topic hint to
   `screen_article_relevance` which:
   1. Chunks via `article_chunker.chunk_article_text`.
   2. Asks the script LLM "is this part of the actual story?" per chunk.
   3. Recomposes the kept chunks, caps at `max_chars`, returns
      `RelevanceResult(excerpt, kept, total_chunks, cache_hit, used_llm)`.
4. Subsequent script generation (Phase 3 validator + creepypasta /
   cartoon / news prompts) sees only the tightened excerpt.
