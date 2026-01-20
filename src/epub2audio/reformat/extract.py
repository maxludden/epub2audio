"""Extract and parse an EPUB table of contents from toc.ncx."""

from __future__ import annotations

import re
# import sys
from pathlib import Path
from typing import Any
import json
from xml.etree import ElementTree as ET
from rich.pretty import Pretty

from epub2audio.utils.logging import get_logger, get_console

logger = get_logger()
console = get_console()

_BACK_MATTER_KEYWORDS = (
    "about the author",
    "acknowledgments",
    "acknowledgements",
    "afterword",
    "also in series",
    "appendix",
    "back matter",
    "bibliography",
    "colophon",
    "contents",
    "copyright",
    "epilogue",
    "glossary",
    "index",
    "notes",
    "other books",
    "permissions",
    "praise",
    "references",
    "resources",
    "thank you",
)

_FONT_EXTENSIONS = (".ttf", ".otf", ".woff", ".woff2")


def _should_skip_entry(title: str, chapter_path: str | None) -> bool:
    """Return True when the TOC entry should be excluded."""
    title_lower = title.strip().lower()
    path_lower = chapter_path.strip().lower() if chapter_path else ""

    if "font" in title_lower or "font" in path_lower:
        return True

    if path_lower.endswith(_FONT_EXTENSIONS):
        return True

    for keyword in _BACK_MATTER_KEYWORDS:
        if keyword in title_lower:
            return True

    return False


def _find_toc_ncx(extracted_dir: Path) -> Path:
    """Locate toc.ncx within an extracted EPUB directory."""
    candidate = extracted_dir / "toc.ncx"
    if candidate.exists():
        logger.trace("Found toc.ncx at root: {path}", path=candidate)
        return candidate
    matches = list(extracted_dir.rglob("toc.ncx"))
    if not matches:
        logger.error("toc.ncx not found under {path}", path=extracted_dir)
        raise FileNotFoundError(f"toc.ncx not found under {extracted_dir}")
    if len(matches) > 1:
        logger.trace(
            "Multiple toc.ncx files found; using first match: {path}", path=matches[0]
        )
    else:
        logger.trace("[i green]Found toc.ncx:[/i green] [b #00ff00]{path}", path=matches[0])
    return matches[0]


def _get_namespace(tag: str) -> str:
    """Return the XML namespace from a tag name, if present."""
    if tag.startswith("{") and "}" in tag:
        return tag.split("}")[0].strip("{")
    return ""


def _parse_chapter_number(title: str | None) -> int | None:
    """Parse an integer chapter number from a title like 'Chapter 12'."""
    logger.trace(f"Entered _parse_chapter_number({title=})")
    if not title:
        logger.trace('No title found. returning `None`')
        return None

    match = re.search(r"^(\d+)\.", title, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def generate_toc(extracted_dir: Path) -> list[dict[str, Any]]:
    """Generate a table of contents from an extracted EPUB folder.

    Returns a list of dicts with:
      - order: int
      - chapter_number: int
      - chapter_title: str
      - chapter_path: str
    """
    logger.trace(f"Entered generate_toc({extracted_dir=}...)")
    extracted_dir = (
        extracted_dir if isinstance(extracted_dir, Path) else Path(extracted_dir)
    )
    if not extracted_dir.exists():
        logger.error(f"Invalid directory: {extracted_dir}")
        raise FileNotFoundError(f"Invalid directory: {extracted_dir}")

    toc_path = _find_toc_ncx(extracted_dir)
    logger.trace(f"Parsing toc.ncx: {toc_path=}")
    tree = ET.parse(toc_path)
    root = tree.getroot()
    ns = _get_namespace(root.tag)

    def q(tag: str) -> str:
        return f"{{{ns}}}{tag}" if ns else tag

    nav_map = root.find(f".//{q('navMap')}")
    if nav_map is None:
        logger.trace(f"No navMap found in toc.ncx: {toc_path}")
        return []

    toc: list[dict[str, Any]] = []
    for order, nav_point in enumerate(nav_map.findall(f".//{q('navPoint')}"), start=1):
        label_node = nav_point.find(f"{q('navLabel')}/{q('text')}")
        # logger.trace(f"{label_node=}")
        title = (label_node.text or "").strip() if label_node is not None else ""
        content_node = nav_point.find(f"{q('content')}")
        chapter_path = content_node.get("src") if content_node is not None else ""
        # play_order = nav_point.get("playOrder")

        chapter_number = _parse_chapter_number(title)
        if chapter_number:
            title = title.lstrip(f"{chapter_number}. ")

        if not chapter_number:
            logger.trace(
                "Skipping TOC entry without chapter number: {title} ({path})",
                title=title or f"order {order}",
                path=chapter_path,
            )
            continue

        if _should_skip_entry(title, chapter_path):
            logger.trace(
                "Skipping TOC entry: {title} ({path})",
                title=title or f"order {order}",
                path=chapter_path,
            )
            continue

        toc.append({
            "order": order,
            "chapter_number": chapter_number or None,
            "chapter_title": title,
            "chapter_path": chapter_path
        })

    logger.trace(
        f"Generated TOC with {len(toc)=} entries from {toc_path=}",
    )

    book_dir = extracted_dir.parent
    json_dir = book_dir / "json"
    if not json_dir.exists():
        logger.trace(f"Creating json directory for TOC: {json_dir=}")
        json_dir.mkdir(parents=True, exist_ok=True)

    TOC_PATH: Path = json_dir / "toc.json" # pylint: disable = C0103:invalid-name
    logger.trace(f'Writing TOC to {TOC_PATH}...')
    with open(TOC_PATH, mode="w", encoding="utf-8") as toc_file:
        json.dump(toc, toc_file, indent=2)
        logger.trace(f"Wrote TOC to {TOC_PATH}!")

    return toc


if __name__ == "__main__":

    _toc: list[dict[str, Any]] = generate_toc(
        Path("static/defiance_of_the_fall_06/extracted")
    )
    console.print(Pretty(_toc, expand_all=True))
