# `src/crawler.py` — Crawler

## Purpose
Fetch trending AI-tool news with a **free default path** (no paid news APIs), optionally using **Firecrawl** when configured in the app/API tab.

## Inputs
- **Optional Firecrawl** (`firecrawl_enabled` + API key, or `FIRECRAWL_API_KEY` in the environment): v2 search for headlines; v1 scrape for article text when `fetch_article_text` is on. On failure or when disabled, Aquaduct falls back automatically.
- Google News RSS query (default in `get_latest_items` / `fetch_latest_items`)
- MarkTechPost homepage (fallback)

### Mode-aware search strings
Headline search combines **topic tags** (if any) with a **video-format bias** (`topic_mode` / `cache_mode` = `news`, `cartoon`, or `explainer`):
- **news** — AI product / release–style phrases.
- **cartoon** — animation / character / series / trailer style (no forced “AI tool” wording).
- **explainer** — explainer / tutorial / education / science slant.

`fetch_latest_items(..., topic_mode=...)` and pipeline fetches pass the current mode so **Discover** and runs match the selected format.

## Outputs
Returns a list of `NewsItem`:
- `title`
- `url`
- `source`
- `published_at` (RSS only, best-effort)

## Dedupe / caching
Persisted under `data/news_cache/`:
- **Per video format**: `seen_<mode>.json` (URLs already used) and `seen_titles_<mode>.json` (title novelty / scoring history), where `<mode>` is `news`, `cartoon`, or `explainer`. The active bucket matches `AppSettings.video_format` (`cache_mode` / `news_cache_mode_for_run()` in `src/topics.py`).
- **Legacy migration**: if `seen_news.json` is missing but flat `seen.json` exists, **news** loads the legacy file once; new writes go to `seen_news.json`. Other formats do not read the legacy flat file.

`fetch_latest_items()` does **not** consult the seen files (used for topic discovery “newest headlines” flows).

## Key functions
- `get_latest_items(..., cache_mode=...)` — fresh headlines with URL dedupe + persist
- `get_scored_items(..., cache_mode=...)` — scored + diversified selection; updates seen URLs and seen titles for that mode
- `clear_news_seen_cache_files(news_cache_dir)` — delete legacy + all per-mode `seen_*.json` / `seen_titles_*.json` (used by the UI “clear cache” action)
- `news_seen_paths(news_cache_dir, mode)` — resolved paths for a mode’s seen files
- `pick_one_item(items)` (currently selects the first fresh item)

