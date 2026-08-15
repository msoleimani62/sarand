"""Rich-based progress reporting for long-running tasks."""

from __future__ import annotations

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from typing import TypeVar

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

T = TypeVar("T")

console = Console(stderr=True)


def create_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )


@contextmanager
def progress_task(
    description: str, total: int | None = None
) -> Generator[tuple[Progress, TaskID], None, None]:
    with create_progress() as progress:
        task_id = progress.add_task(description, total=total)
        yield progress, task_id


def track(
    iterable: Iterable[T], description: str, total: int | None = None
) -> Iterable[T]:
    # A total=0 progress bar renders stuck at "0% -:--:--" forever in
    # rich, which looks hung even though there's genuinely nothing to
    # do (e.g. every file was a --cache hit). Skip the bar entirely for
    # empty work -- this protects every current and future call site,
    # not just the one that surfaced it.
    # نوار پیشرفت با total=0 در rich برای همیشه روی «0% -:--:--» گیر
    # می‌کند، در حالی‌که واقعاً کاری برای انجام نیست (مثلاً همه‌ی فایل‌ها
    # cache hit بودند). برای کار خالی، نوار را کامل رد می‌کنیم -- این از
    # هر نقطه‌ی فراخوانی فعلی و آینده محافظت می‌کند، نه فقط همانی که
    # مشکل را نشان داد.
    if total == 0:
        return
    from rich.progress import track as rich_track

    yield from rich_track(
        iterable, description=description, total=total, console=console
    )


def status(message: str) -> None:
    console.print(f"[cyan]→[/cyan] {message}")


def success(message: str) -> None:
    console.print(f"[green]✓[/green] {message}")


def warning(message: str) -> None:
    console.print(f"[yellow]![/yellow] {message}")


def error(message: str) -> None:
    console.print(f"[red]✗[/red] {message}")
