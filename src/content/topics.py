from __future__ import annotations

from src.core.config import VIDEO_FORMATS, AppSettings


def normalize_video_format(value: str | None) -> str:
    t = (value or "news").strip().lower()
    return t if t in VIDEO_FORMATS else "news"


def video_format_uses_news_style_sourcing(value: str | None) -> bool:
    """News and Explainer share the same headline search bias (AI / product news) and news-style script defaults."""
    v = normalize_video_format(value)
    return v in ("news", "explainer")


def discover_uses_headline_sources(value: str | None) -> bool:
    """Topic Discover + crawl fallbacks: Google News / MarkTechPost only for news + explainer (headline-ish)."""
    return video_format_uses_news_style_sourcing(value)


def effective_topic_tags(app: AppSettings) -> list[str]:
    """Tags for the current pipeline mode (`video_format`)."""
    m = getattr(app, "topic_tags_by_mode", None) or {}
    vf = normalize_video_format(getattr(app, "video_format", None))
    lst = m.get(vf)
    return list(lst) if isinstance(lst, list) else []


def topic_tags_for_mode(app: AppSettings, mode: str) -> list[str]:
    """Tags stored for a given mode (e.g. news list for topic discovery)."""
    m = getattr(app, "topic_tags_by_mode", None) or {}
    key = normalize_video_format(mode)
    lst = m.get(key)
    return list(lst) if isinstance(lst, list) else []


def news_cache_mode_for_run(app: AppSettings) -> str:
    """Which URL/title dedupe bucket to use (matches `video_format`)."""
    return normalize_video_format(getattr(app, "video_format", None))


def video_format_skips_seen_url_disk_cache(value: str | None) -> bool:
    """Preset modes that fetch fresh URLs each run without persisting seen_<mode>.json (Firecrawl-heavy)."""
    return normalize_video_format(value) in ("unhinged", "creepypasta")


def video_format_is_creative_topics_mode(value: str | None) -> bool:
    """Topics tab Discover: web-first creative sourcing (not Google News headline lists)."""
    return normalize_video_format(value) in ("cartoon", "unhinged", "creepypasta")


def video_format_writes_topic_research_pack(value: str | None) -> bool:
    """After Discover, persist topic_research manifest + images (creative modes and health_advice)."""
    v = normalize_video_format(value)
    return v in ("cartoon", "unhinged", "creepypasta", "health_advice")
