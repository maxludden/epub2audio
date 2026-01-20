#!/usr/bin/env python3
"""Top-level CLI for converting EPUBs into audiobooks."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from epub2audio.audio.narrate_chapters import narrate_chapters
from epub2audio.reformat.convert_html import convert_to_html
from epub2audio.reformat.convert_markdown import convert_to_markdown
from epub2audio.reformat.create_audiobook import _build_audiobook
from epub2audio.reformat.extract import generate_toc
from epub2audio.reformat.reformat import reformat_epub, unzip_epub_zip
from epub2audio.utils.logging import get_logger, get_progress

app = typer.Typer(add_completion=False)
logger = get_logger()
progress = get_progress()


@app.command()
def convert(
    epub: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    *,
    base_dir: Path = typer.Option(Path("static"), help="Base directory for book data."),
    copy_to_epub_dir: bool = typer.Option(
        True, help="Copy the EPUB into the book folder."
    ),
    slugify_stem: bool = typer.Option(True, help="Slugify the EPUB stem for storage."),
    unzip_overwrite: bool = typer.Option(
        True, help="Overwrite extracted contents if present."
    ),
    narrate_start: int | None = typer.Option(
        None, help="Start chapter number to narrate."
    ),
    narrate_end: int | None = typer.Option(None, help="End chapter number to narrate."),
    narrate_skip_existing: bool = typer.Option(
        True, help="Skip chapters with existing audio."
    ),
    narrate_overwrite: bool = typer.Option(
        True, help="Overwrite existing audio when narrating."
    ),
    output: Path | None = typer.Option(
        None, help="Output .m4b path (defaults to static/<stem>/audio/<title>.m4b)."
    ),
) -> Path:
    """Run the full EPUB -> audiobook pipeline with progress logging."""
    if epub.suffix.lower() != ".epub":
        raise typer.BadParameter("Input must be an .epub file.")

    with progress:
        task = progress.add_task("Preparing EPUB...", total=7)
        zip_path = reformat_epub(
            epub,
            base_dir=base_dir,
            copy_to_epub_dir=copy_to_epub_dir,
            slugify_stem=slugify_stem,
        )
        stem = zip_path.stem
        progress.update(task, advance=1, description="Extracting EPUB...")

        extracted_root = unzip_epub_zip(
            zip_path,
            overwrite=unzip_overwrite,
        )
        progress.update(task, advance=1, description="Generating TOC...")
        generate_toc(extracted_root)

        progress.update(task, advance=1, description="Copying HTML chapters...")
        convert_to_html(stem, base_dir=base_dir)

        progress.update(task, advance=1, description="Converting to Markdown...")
        convert_to_markdown(stem, base_dir=base_dir)
        
        progress.update(task, advance=1, description="Narrating chapters...")

        toc_path = base_dir / stem / "json" / "toc.json"
        if toc_path.exists():
            toc_entries = json.loads(toc_path.read_text(encoding="utf-8"))
            markdown_chapters = [
                entry.get("chapter_number")
                for entry in toc_entries
                if entry.get("markdown") and entry.get("chapter_number") is not None
            ]
            markdown_chapters = [
                int(value)
                for value in markdown_chapters
                if isinstance(value, int)
                or (isinstance(value, str) and value.isdigit())
            ]
            if markdown_chapters:
                if narrate_start is None:
                    narrate_start = min(markdown_chapters)
                if narrate_end is None:
                    narrate_end = max(markdown_chapters)

        narrate_chapters(
            stem,
            base_dir=base_dir,
            start=narrate_start,
            end=narrate_end,
            skip_existing=narrate_skip_existing,
            overwrite=narrate_overwrite,
        )
        progress.update(task, advance=1, description="Building audiobook...")

        output_path = _build_audiobook(
            stem=stem,
            base_dir=base_dir,
            output=output,
        )
        progress.update(task, advance=1, description="Done.")

    logger.info("Audiobook created at {path}", path=output_path)
    return output_path


if __name__ == "__main__":
    app()
