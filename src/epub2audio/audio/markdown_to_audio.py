#!/usr/bin/env python3
"""
Convert a Markdown file into a single audiobook using macOS `say`.

Pipeline:
1. Read Markdown
2. Generate a single narration track via `say`
3. Transcode to the requested output format
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

# from rich.panel import Panel
from rich_gradient.panel import Panel

import typer

from epub2audio.utils.logging import get_logger, get_progress

app = typer.Typer(add_completion=False)
logger = get_logger()
progress = get_progress()
_console = progress.console



# ------------------------------
# Audio generation
# ------------------------------

def say_to_file(text: str, output: Path) -> None:
    """Generate audio for text using macOS `say`."""
    tmp_text_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            encoding="utf-8",
            delete=False,
        ) as tmp_text:
            tmp_text.write(text)
            tmp_text_path = Path(tmp_text.name)

        cmd = ["say", "-o", str(output), "-f", str(tmp_text_path)]
        subprocess.run(cmd, check=True)
    finally:
        if tmp_text_path is not None:
            tmp_text_path.unlink(missing_ok=True)

def transcode_audio(input_path: Path, output: Path) -> None:
    """Transcode audio to the requested format using ffmpeg."""
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    if output.suffix.lower() in {".m4a", ".m4b", ".mp4"}:
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"])
    cmd.append(str(output))
    subprocess.run(cmd, check=True)


# ------------------------------
# CLI
# ------------------------------

@app.command()
def generate(
    markdown: Path = typer.Argument(..., exists=True, readable=True),
    output: Path = typer.Option(
        Path("audiobook.m4a"),
        "--output",
        "-o",
        help="Final audiobook output file",
    )
) -> None:
    """
    Convert a Markdown file into a single spoken audiobook.
    """
    with _console.status(
        f"[i #999]Reading markdown:[/] [b #9f0]{markdown.stem}[/][#999]...[/]",
        spinner="point"):

        logger.trace(f"Reading markdown: {markdown.stem}...")

        text = markdown.read_text(encoding="utf-8")
        text = text.lstrip('#')
        text = text.strip()
        if not text:
            logger.error("No speakable content found.")
            raise typer.Exit(code=1)

        line_count = text.count("\n") + 1
        narrate_msg = f"{line_count} lines to narrate..."
        logger.trace(f"{narrate_msg}")
        msg = output.stem

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            audio_tmp_file = Path(tmp)
            raw_audio_path = audio_tmp_file / "narration.aiff"

            say_to_file(text, raw_audio_path)

            if output.suffix.lower() in {".aiff", ".aif"}:
                raw_audio_path.replace(output)
            else:
                logger.info("Transcoding audio")
                transcode_audio(raw_audio_path, output)

        logger.trace(f"Chapter narrated: {output.resolve()}")
        progress.console.print(
            Panel(
                f"Narrated {msg}!",
                title="Success!",
                colors=['#9f0','#0f0', '#0f9'],
                title_style="b #fff"
            )
        )
    return


if __name__ == "__main__":
    app()
