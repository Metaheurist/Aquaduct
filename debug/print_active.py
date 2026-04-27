"""Shim for ``python -m debug.print_active`` → ``debug.tools.print_active``."""

from __future__ import annotations

from debug.tools.print_active import main

if __name__ == "__main__":
    main()
