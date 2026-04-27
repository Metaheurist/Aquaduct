"""Print resolved debug categories (env + CLI + MODULE_DEBUG_FLAGS). Run: ``python -m debug.tools.print_active``."""

from __future__ import annotations

from debug.debug_log import (
    DEBUG_CATEGORIES,
    MODULE_DEBUG_FLAGS,
    active_categories,
    invalidate_debug_cache,
)


def main() -> None:
    invalidate_debug_cache()
    act = active_categories()
    print("DEBUG_CATEGORIES:", ", ".join(DEBUG_CATEGORIES))
    print()
    print("MODULE_DEBUG_FLAGS (edit debug/debug_log.py to toggle):")
    for c in DEBUG_CATEGORIES:
        print(f"  {c}: {MODULE_DEBUG_FLAGS.get(c, False)}")
    print()
    print(f"Resolved active_categories ({len(act)}):")
    for c in sorted(act):
        print(f"  + {c}")
    print()
    print("Hints: AQUADUCT_DEBUG=all | cat1,cat2 | AQUADUCT_DEBUG_PIPELINE=1")
    print("CLI: python -m UI --debug ui,workers")


if __name__ == "__main__":
    main()
