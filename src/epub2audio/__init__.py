"""Initialize epub2audio library."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.progress import Progress
from rich.console import Console

from epub2audio.utils import get_console, get_logger, get_progress

if TYPE_CHECKING:
    from loguru._logger import Logger

progress: Progress = get_progress(console=get_console())
_console: Console = progress.console
log: Logger = get_logger(console=_console)
