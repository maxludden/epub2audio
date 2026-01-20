"""Shared Loguru + Rich logging configuration for epub2audio."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from rich import get_console as rich_get_console
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.traceback import install as tr_install

if TYPE_CHECKING:
    from loguru._logger import Logger

TRACE_FORMAT = "{time:HH:mm:ss.SSS}|{level:^8}| Module:{module} \
| {function} | Line {line:^5}|{message}"


def get_console(console: Console | None = None) -> Console:
    """Create a Rich console for app output."""
    if console is None:
        console = rich_get_console()
    tr_install(console=console)
    return console


def get_progress(console: Console | None = None) -> Progress:
    """Create a Rich Progress instance using the provided console."""
    if console is None:
        console = get_console()
    return Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TimeElapsedColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )


def get_logger(
    log_path: Path | str = Path("logs/trace.log"),
    level: str = "DEBUG",
    trace_level: str = "TRACE",
    console: Console | None = None,
) -> Logger:
    """Configure Loguru with a file sink and Rich console sink.

    Args:
        log_path: File path for trace logs.
        level: Console log level.
        trace_level: File sink level.
    Returns:
        Configured Loguru logger.
    """
    if console is None:
        console = get_console()

    logger.remove()
    logger.add(
        str(log_path),
        level=trace_level,
        mode="a",
        colorize=False,
        format=TRACE_FORMAT,
    )
    logger.add(
        RichHandler(level=level, markup=True, rich_tracebacks=True, console=console),
        level=level,
        format="{message}",
        backtrace=False,
        diagnose=False,
    )
    return logger  # type: ignore
