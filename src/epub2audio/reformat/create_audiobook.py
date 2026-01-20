#!/usr/bin/env python3
"""Build an M4B audiobook from chapter audio files with chapters + cover art."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import typer

from epub2audio.utils.logging import get_logger

app = typer.Typer(add_completion=False)
logger = get_logger()


def _load_toc(toc_path: Path) -> list[dict[str, Any]]:
    """Load toc.json entries from disk."""
    if not toc_path.exists():
        raise FileNotFoundError(f"toc.json not found: {toc_path}")
    return json.loads(toc_path.read_text(encoding="utf-8"))


def _normalize_title(value: str) -> str:
    """Normalize a title for fuzzy matching against filenames."""
    lowered = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(cleaned.split())


def _humanize_stem(stem: str) -> str:
    """Convert a stem into a title-cased name with de-padded numbers."""
    parts = re.split(r"[^a-zA-Z0-9]+", stem.strip())
    words: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            words.append(str(int(part)))
        else:
            words.append(part)
    return " ".join(words).title()


def _index_audio_files(audio_root: Path) -> tuple[dict[int, Path], dict[str, Path]]:
    """Index audio files by leading number and normalized title."""
    by_number: dict[int, Path] = {}
    by_title: dict[str, Path] = {}
    if not audio_root.exists():
        return by_number, by_title

    for path in sorted(audio_root.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".m4a", ".m4b", ".mp3", ".aac"}:
            continue
        stem = path.stem
        match = re.match(r"^\s*(\d+)\s*[.\-–:_)]\s*(.*)$", stem)
        if match:
            number = int(match.group(1))
            by_number.setdefault(number, path)
            title_part = match.group(2).strip()
        else:
            title_part = stem
        if title_part:
            by_title.setdefault(_normalize_title(title_part), path)
    return by_number, by_title


def _escape_ffmetadata(value: str) -> str:
    """Escape a metadata value for ffmetadata format."""
    return (
        value.replace("\\", "\\\\")
        .replace("\n", " ")
        .replace("=", "\\=")
        .replace(";", "\\;")
        .replace("#", "\\#")
    )


def _ffprobe_duration_ms(path: Path) -> int:
    """Return the duration of an audio file in milliseconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    output = subprocess.check_output(cmd, text=True).strip()
    seconds = float(output)
    return max(0, int(round(seconds * 1000)))


def _find_cover(extracted_dir: Path) -> Path | None:
    """Locate the cover image for the extracted EPUB."""
    candidate = extracted_dir / "cover.jpeg"
    if candidate.exists():
        return candidate
    for name in ("cover.jpg", "cover.png", "cover.jpeg"):
        for path in extracted_dir.rglob(name):
            return path
    return None


def _find_opf(extracted_dir: Path) -> Path | None:
    """Locate the OPF metadata file for the extracted EPUB."""
    if not extracted_dir.exists():
        return None
    candidates = sorted(extracted_dir.rglob("*.opf"))
    return candidates[0] if candidates else None


def _load_opf_metadata(opf_path: Path) -> tuple[str | None, list[str]]:
    """Load title and creators from an OPF file."""
    try:
        tree = ElementTree.parse(opf_path)
    except ElementTree.ParseError as exc:
        raise ValueError(f"Invalid OPF metadata file: {opf_path}") from exc

    root = tree.getroot()
    ns = {"dc": "http://purl.org/dc/elements/1.1/"}

    title_node = root.find(".//dc:title", ns)
    title = title_node.text.strip() if title_node is not None and title_node.text else None

    creators: list[str] = []
    for creator in root.findall(".//dc:creator", ns):
        if creator.text and creator.text.strip():
            creators.append(creator.text.strip())

    return title, creators


def _build_concat_list(paths: list[Path], output_path: Path | None, stem: str) -> None:
    """Write ffmpeg concat demuxer list for the input audio paths."""
    if output_path is None:
        output_path = Path("static") / stem / "txt" / "concat.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for path in paths:
        safe_path = str(path.resolve()).replace("'", "'\\''")
        logger.trace(f"Appending {safe_path=} to lines...")
        lines.append(f"file '{safe_path}'")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_ffmetadata(
    entries: list[dict[str, Any]],
    audio_paths: list[Path],
    output_path: Path,
    book_title: str,
    author: str | None,
) -> None:
    """Write ffmetadata chapters file aligned to the audio files."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [";FFMETADATA1", f"title={_escape_ffmetadata(book_title)}"]
    if author:
        escaped_author = _escape_ffmetadata(author)
        lines.extend([f"artist={escaped_author}", f"album_artist={escaped_author}"])
    current_ms = 0
    for entry, audio_path in zip(entries, audio_paths, strict=True):
        duration_ms = _ffprobe_duration_ms(audio_path)
        raw_title = entry.get("chapter_title") or audio_path.stem
        chapter_number = entry.get("chapter_number")
        if chapter_number:
            if raw_title:
                title = f"Chapter {chapter_number}: {raw_title}"
            else:
                title = f"Chapter {chapter_number}"
        else:
            title = raw_title
        lines.extend(
            [
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={current_ms}",
                f"END={current_ms + duration_ms}",
                f"title={_escape_ffmetadata(str(title))}",
            ]
        )
        current_ms += duration_ms
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_audiobook(
    *,
    stem: str,
    base_dir: Path,
    output: Path | None,
) -> Path:
    """Create an M4B audiobook with chapters and cover art."""
    book_dir = base_dir / stem
    toc_path = book_dir / "json" / "toc.json"
    logger.info("Loading TOC: {path}", path=toc_path)
    entries = sorted(_load_toc(toc_path), key=lambda item: item.get("order", 0))

    audio_root = book_dir / "audio"
    by_number, by_title = _index_audio_files(audio_root)

    audio_paths: list[Path] = []
    used_entries: list[dict[str, Any]] = []
    for entry in entries:
        audio_value = entry.get("audio")
        if not audio_value:
            audio_path = None
        else:
            audio_path = Path(audio_value)
            if not audio_path.is_absolute() and not audio_path.exists():
                audio_path = audio_root / audio_path
            if not audio_path.exists():
                audio_path = None

        if audio_path is None:
            chapter_number = entry.get("chapter_number")
            if isinstance(chapter_number, int) and chapter_number in by_number:
                audio_path = by_number[chapter_number]
            elif isinstance(chapter_number, str) and chapter_number.isdigit():
                audio_path = by_number.get(int(chapter_number))
            if audio_path is None:
                order = entry.get("order")
                if isinstance(order, int) and order in by_number:
                    audio_path = by_number[order]

        if audio_path is None:
            title = entry.get("chapter_title")
            if isinstance(title, str) and title.strip():
                audio_path = by_title.get(_normalize_title(title))

        if audio_path is None:
            logger.warning(
                "No audio match for TOC entry: {title}",
                title=entry.get("chapter_title") or entry.get("order"),
            )
            continue

        audio_paths.append(audio_path)
        used_entries.append(entry)

    if not audio_paths:
        raise FileNotFoundError(f"No audio files found under {audio_root}")

    book_title = _humanize_stem(stem)
    extracted_root = book_dir / "extracted"
    cover_path = _find_cover(extracted_root)
    if cover_path is None:
        raise FileNotFoundError(f"Cover image not found under {extracted_root}")
    logger.info("Using cover: {path}", path=cover_path)
    logger.info("Found {count} audio files", count=len(audio_paths))

    author: str | None = None
    opf_path = _find_opf(extracted_root)
    if opf_path:
        try:
            opf_title, creators = _load_opf_metadata(opf_path)
            if opf_title:
                logger.info("OPF title: {title}", title=opf_title)
                book_title = opf_title
            if creators:
                author = " & ".join(creators)
                logger.info("OPF author: {author}", author=author)
        except ValueError as exc:
            logger.warning("Failed to parse OPF metadata: {error}", error=str(exc))

    if output is None:
        output = audio_root / f"{book_title}.m4b"
    output.parent.mkdir(parents=True, exist_ok=True)
    txt_dir = book_dir / "txt"
    concat_list = txt_dir / "concat.txt"
    ffmetadata = txt_dir / "chapters.txt"
    _build_concat_list(audio_paths, concat_list, stem=stem)
    _build_ffmetadata(used_entries, audio_paths, ffmetadata, str(book_title), author)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-f",
        "ffmetadata",
        "-i",
        str(ffmetadata),
        "-i",
        str(cover_path),
        "-map",
        "0:a",
        "-map",
        "2:v",
        "-c",
        "copy",
        "-map_metadata",
        "1",
        "-disposition:v:0",
        "attached_pic",
        "-movflags",
        "+faststart",
        str(output),
    ]
    logger.info("Running ffmpeg to build {path}", path=output)
    subprocess.run(cmd, check=True)

    return output


@app.command()
def create(
    stem: str = typer.Option("defiance_of_the_fall_06", help="Book stem folder name"),
    base_dir: Path = typer.Option(Path("static"), help="Base directory with book folders"),
    output: Path | None = typer.Option(
        None, help="Output .m4b path (defaults to static/<stem>/audio/<title>.m4b)"
    ),
) -> None:
    """Create an M4B audiobook from chapter audio files listed in toc.json."""
    _build_audiobook(
        stem=stem,
        base_dir=base_dir,
        output=output,
    )


if __name__ == "__main__":
    app()
