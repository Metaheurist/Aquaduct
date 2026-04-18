"""
Optional Rich-based progress bars + dim pip log for ``torch_install`` CLI (TTY only).

Set ``AQUADUCT_PLAIN_CLI=1`` or pass ``--plain`` to force plain ``print`` output.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.progress import TaskID


def use_rich_cli() -> bool:
    if os.environ.get("AQUADUCT_PLAIN_CLI", "").strip():
        return False
    if not sys.stdout.isatty():
        return False
    try:
        import rich  # noqa: F401
    except ImportError:
        return False
    return True


def _truncate(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


@contextmanager
def rich_pip_install_session(*, with_requirements_phase: bool) -> Iterator[Callable[[str], None]]:
    """
    Progress bar(s) for pip install. Yields ``on_line`` compatible with torch_install.
    """
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    from src.torch_install import pip_download_percent, pip_line_hint

    console = Console()
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=36),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[hint]}"),
        TimeElapsedColumn(),
        console=console,
        expand=True,
    ) as progress:
        task_torch: TaskID = progress.add_task("PyTorch", total=100, hint="…")
        task_req: TaskID | None = None
        if with_requirements_phase:
            task_req = progress.add_task("requirements.txt", total=100, hint="waiting…", start=False)

        phase: list[str] = ["torch"]

        def on_line(line: str) -> None:
            s = line.rstrip()
            if not s:
                return
            console.print(s, style="dim", overflow="ellipsis", crop=True)
            if (
                with_requirements_phase
                and task_req is not None
                and "# Installing packages from requirements.txt" in s
            ):
                phase[0] = "req"
                progress.start_task(task_req)
                progress.update(task_torch, completed=100, hint="done")
            tid = task_req if phase[0] == "req" and task_req is not None else task_torch
            pct = pip_download_percent(s)
            hint = pip_line_hint(s) or _truncate(s, 100)
            if pct is not None:
                progress.update(tid, completed=pct, hint=_truncate(hint, 70))
            else:
                progress.update(tid, hint=_truncate(hint, 70))

        yield on_line


@contextmanager
def rich_windows_wheels_session(
    variant_names: tuple[str, ...],
) -> Iterator[tuple[Callable[[str], None], Callable[[str], None]]]:
    """
    Multi-task progress for ``--download-all-windows-wheels``.
    Yields ``(on_line, on_variant_start)``.
    """
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    from src.torch_install import pip_download_percent, pip_line_hint

    console = Console()
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[hint]}"),
        TimeElapsedColumn(),
        console=console,
        expand=True,
    ) as progress:
        tasks: dict[str, TaskID] = {
            n: progress.add_task(f"download [{n}]", total=100, hint="pending…") for n in variant_names
        }
        current: list[str | None] = [None]

        def on_variant_start(name: str) -> None:
            current[0] = name
            tid = tasks[name]
            try:
                progress.reset(tid)
            except Exception:
                progress.update(tid, completed=0, hint="starting…")

        def on_line(line: str) -> None:
            s = line.rstrip()
            if not s:
                return
            console.print(s, style="dim", overflow="ellipsis", crop=True)
            name = current[0]
            if name and name in tasks:
                tid = tasks[name]
                pct = pip_download_percent(s)
                hint = pip_line_hint(s) or _truncate(s, 100)
                if pct is not None:
                    progress.update(tid, completed=pct, hint=_truncate(hint, 65))
                else:
                    progress.update(tid, hint=_truncate(hint, 65))

        yield on_line, on_variant_start
