#!/usr/bin/env python3
"""Convert toc.json markdown entries into per-chapter audio files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from epub2audio.audio import markdown_to_audio
from epub2audio.utils.logging import get_logger, get_progress

app = typer.Typer(add_completion=False)
logger = get_logger()
progress = get_progress()


def _load_toc(toc_path: Path) -> list[dict[str, Any]]:
    if not toc_path.exists():
        raise FileNotFoundError(f"toc.json not found: {toc_path}")
    return json.loads(toc_path.read_text(encoding="utf-8"))


def _audio_path_from_entry(
    entry: dict[str, Any],
    *,
    book_dir: Path,
) -> Path | None:
    audio = entry.get("audio")
    if audio:
        return Path(audio)

    chapter_label = entry.get("chapter_number") or entry.get("order")
    if chapter_label is None:
        return None

    chapter_title = entry.get("chapter_title") or f"Chapter {chapter_label}"
    title_for_audio = str(chapter_title).strip()
    audio_name = f"{chapter_label}. {title_for_audio}.m4a"
    return book_dir / "audio" / audio_name


@app.command()
def convert_from_toc(
    stem: str,
    *,
    base_dir: Path = Path("static"),
    overwrite: bool = True,
    skip_existing: bool = True,
    start: int | None = None,
    end: int | None = None,
) -> list[Path]:
    """Convert markdown chapters listed in toc.json into audio files."""
    book_dir = base_dir / stem
    toc_path = book_dir / "json" / "toc.json"
    toc_entries = _load_toc(toc_path)

    if start is None or end is None:
        markdown_chapters = [
            entry.get("chapter_number")
            for entry in toc_entries
            if entry.get("markdown") and entry.get("chapter_number") is not None
        ]
        markdown_chapters = [
            int(value)
            for value in markdown_chapters
            if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
        ]
        if markdown_chapters:
            if start is None:
                start = min(markdown_chapters)
            if end is None:
                end = max(markdown_chapters)
            logger.info(
                "Narration range from markdown: {start} to {end}",
                start=start,
                end=end,
            )

    chapters: dict[int, dict[str, Any]] = {}
    for entry in toc_entries:
        chapter_number = entry.get("chapter_number")
        if chapter_number is None:
            continue
        if isinstance(chapter_number, int):
            chapter_key = chapter_number
        else:
            try:
                chapter_key = int(chapter_number)
            except (TypeError, ValueError):
                continue
        chapters[chapter_key] = entry
    if not chapters:
        logger.warning("No chapters found in toc.json: {path}", path=toc_path)
        return []

    if start is None:
        start = min(chapters)
    if end is None:
        end = max(chapters)
    assert start in chapters, f"Start chapter not valid: {start}"
    assert end in chapters, f"End chapter not valid: {end}"
    total_chapters = end - start + 1

    written: list[Path] = []
    with progress:
        task = progress.add_task(
            f"Narrating Chapter {start} to Chapter {end}...", total=total_chapters
        )
        for chapter_label in sorted(chapters):
            entry = chapters[chapter_label]
            if start is not None and chapter_label < start:
                progress.advance(task)
                continue
            if end is not None and chapter_label > end:
                progress.advance(task)
                continue
            md_path_value = entry.get("markdown")
            if not md_path_value:
                progress.advance(task)
                continue
            md_path = Path(md_path_value)
            if not md_path.exists():
                logger.warning("Markdown missing: {path}", path=md_path)
                progress.advance(task)
                continue

            output_path = _audio_path_from_entry(entry, book_dir=book_dir)
            if not output_path:
                progress.advance(task)
                continue

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists() and skip_existing and not overwrite:
                logger.debug("Audio exists; skipping: {path}", path=output_path)
                progress.advance(task)
                continue

            markdown_to_audio.generate(markdown=md_path, output=output_path)
            written.append(output_path)
            progress.advance(task)

    logger.info("Generated {count} audio files", count=len(written))
    return written


if __name__ == "__main__":
    app()
