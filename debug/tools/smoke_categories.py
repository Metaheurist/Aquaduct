"""Emit one ``dprint`` line per category (respects active flags only). Run: ``python -m debug.tools.smoke_categories``."""

from __future__ import annotations

from debug.debug_log import DEBUG_CATEGORIES, dprint, invalidate_debug_cache


def main() -> None:
    invalidate_debug_cache()
    for cat in DEBUG_CATEGORIES:
        dprint(cat, "smoke_categories probe ok")


if __name__ == "__main__":
    main()
