# `src/crawler.py` — Crawler

## Purpose
Fetch trending AI-tool news **without paid APIs**, returning a small list of new items.

## Inputs
- Google News RSS query (default in `get_latest_items`)
- MarkTechPost homepage (fallback)

## Outputs
Returns a list of `NewsItem`:
- `title`
- `url`
- `source`
- `published_at` (RSS only, best-effort)

## Dedupe / caching
Persisted in:
- `data/news_cache/seen.json`

URLs already in `seen.json` are skipped so Aquaduct doesn’t regenerate the same story repeatedly.

## Key functions
- `get_latest_items(news_cache_dir, limit=3, query=...)`
- `pick_one_item(items)` (currently selects the first fresh item)

