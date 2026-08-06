"""Rich-based progress reporting for long-running tasks."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Iterable, Optional, TypeVar

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
def progress_task(description: str, total: Optional[int] = None) -> Generator[tuple[Progress, TaskID], None, None]:
    with create_progress() as progress:
        task_id = progress.add_task(description, total=total)
        yield progress, task_id


def track(iterable: Iterable[T], description: str, total: Optional[int] = None) -> Iterable[T]:
    from rich.progress import track as rich_track

    yield from rich_track(iterable, description=description, total=total, console=console)


def status(message: str) -> None:
    console.print(f"[cyan]→[/cyan] {message}")


def success(message: str) -> None:
    console.print(f"[green]✓[/green] {message}")


def warning(message: str) -> None:
    console.print(f"[yellow]![/yellow] {message}")


def error(message: str) -> None:
    console.print(f"[red]✗[/red] {message}")
