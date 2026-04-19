from __future__ import annotations

from src.core.config import VIDEO_FORMATS, AppSettings


def normalize_video_format(value: str | None) -> str:
    t = (value or "news").strip().lower()
    return t if t in VIDEO_FORMATS else "news"


def video_format_uses_news_style_sourcing(value: str | None) -> bool:
    """News and Explainer share the same headline search bias (AI / product news) and news-style script defaults."""
    v = normalize_video_format(value)
    return v in ("news", "explainer")


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
