# `src/content/crawler.py` — Crawler

## Purpose
Fetch trending AI-tool news with a **free default path** (no paid news APIs), optionally using **Firecrawl** when configured in the app/API tab.

**Desktop Run → Custom** (`AppSettings.run_content_mode == "custom"`) does **not** use the crawler for script sourcing on that run; the pipeline uses user instructions and synthetic `sources` metadata instead (see [Main loop](../pipeline/main.md), [Brain](../pipeline/brain.md)).

## Inputs
- **Optional Firecrawl** (`firecrawl_enabled` + API key, or `FIRECRAWL_API_KEY` in the environment): v2 search for headlines; v1 scrape for article text when `fetch_article_text` is on. On failure or when disabled, Aquaduct falls back automatically.
- Google News RSS query — used only when **`discover_uses_headline_sources()`** is true (**news** and **explainer** modes).
- MarkTechPost homepage — same headline-style fallback, **news/explainer only**.

### Mode-aware search strings
Search combines **topic tags** (if any) with a **video-format bias** (`topic_mode` / `cache_mode`):
- **news** and **explainer** — **same** AI product / release–style queries (`video_format_uses_news_style_sourcing()` in [`src/content/topics.py`](../../src/content/topics.py)); Google News RSS + MarkTechPost may supplement Firecrawl.
- **cartoon** and **unhinged** — Firecrawl queries bias toward **animation / cartoon / meme / absurdist** language (not generic “sketch comedy” SEO or listicles). Extra alternate queries favor webcomics, animated shorts, and chaotic cartoon memes. In the **Topics → Discover** UI only, Google News RSS and MarkTechPost are skipped (`topic_discover_only=True`). For **runs, storyboard, and `get_scored_items`**, if Firecrawl still returns nothing, RSS + MarkTechPost are used as a last resort so the pipeline is not empty. Topic phrase extraction ([`src/content/topic_discovery.py`](../../src/content/topic_discovery.py)) drops listicle titles and bare platform names for these modes.

`fetch_latest_items(..., topic_mode=...)` and pipeline fetches pass the current mode so **Discover** and runs match the selected format.

## Outputs
Returns a list of `NewsItem`:
- `title`
- `url`
- `source`
- `published_at` (RSS only, best-effort)
- `image_url` (optional; Firecrawl v2 search preview when the API returns it)

## Topic research pack (Cartoon / Unhinged Discover)
When you click **Discover** on the **Topics** tab for **Cartoon** or **Cartoon (unhinged)**, the app saves a small research bundle under **`.Aquaduct_data/data/topic_research/<cartoon|unhinged>/`** — see [`src/content/topic_research_assets.py`](../../src/content/topic_research_assets.py) (`manifest.json` + downloaded preview images). The latest manifest is also turned into markdown and prepended to **`build_script_context`** `extra_markdown` during runs / preview / storyboard when story web context or reference-image gathering runs ([`main.py`](../../main.py), [`UI/workers.py`](../../UI/workers.py)), so the script LLM sees those URLs and local image paths as extra context.

## Dedupe / caching
Persisted under `data/news_cache/`:
- **Per video format**: `seen_<mode>.json` (URLs already used) and `seen_titles_<mode>.json` (title novelty / scoring history), where `<mode>` is `news`, `cartoon`, or `explainer`. The active bucket matches `AppSettings.video_format` (`cache_mode` / `news_cache_mode_for_run()` in `src/content/topics.py`).
- **Legacy migration**: if `seen_news.json` is missing but flat `seen.json` exists, **news** loads the legacy file once; new writes go to `seen_news.json`. Other formats do not read the legacy flat file.

`fetch_latest_items()` does **not** consult the seen files (used for topic discovery). For **news/explainer** that still means “newest headline-like” results; for **cartoon/unhinged** in **Discover** it means creative seeds without forcing Google News; for **pipeline** fetches, RSS may still backfill when Firecrawl is empty.

## Key functions
- `fetch_latest_items(..., topic_discover_only=False)` — uncached fetch; set `topic_discover_only=True` only for the Topics tab **Discover** button (creative modes skip headline RSS in that path).
- `get_latest_items(..., cache_mode=...)` — fresh headlines with URL dedupe + persist
- `get_scored_items(..., cache_mode=...)` — scored + diversified selection; updates seen URLs and seen titles for that mode
- `clear_news_seen_cache_files(news_cache_dir)` — delete legacy + all per-mode `seen_*.json` / `seen_titles_*.json` (used by the UI “clear cache” action)
- `news_seen_paths(news_cache_dir, mode)` — resolved paths for a mode’s seen files
- `pick_one_item(items)` (currently selects the first fresh item)

