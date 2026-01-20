"""Convert extracted EPUB chapters into markdown files."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from epub2audio.reformat.convert_html import RULE_SVG, _resolve_chapter_path
from epub2audio.utils.logging import get_logger, get_progress

logger = get_logger()
progress = get_progress()

RULE_MD_BLOCK = ":::: class_sfp\n::: class_sfj\n![](rule.svg){.class_sfg}\n:::\n::::"
RULE_MD_REPLACEMENT = (
    '<div style="max-width:75%;margin:auto;">\n'
    '    <img src="rule.svg">\n'
    "</div>"
)


def _pandoc_html_to_markdown(html_text: str) -> str:
    """Convert HTML to markdown using pandoc."""
    if shutil.which("pandoc") is None:
        raise FileNotFoundError("pandoc is required but was not found on PATH")
    result = subprocess.run(
        ["pandoc", "-f", "html", "-t", "gfm"],
        input=html_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pandoc failed: {result.stderr.strip()}")
    return result.stdout.strip() + "\n"


def _postprocess_markdown(markdown: str, chapter_title: str, chapter_number: int | None) -> str:
    """Post-process pandoc markdown output for custom formatting."""
    # remove page ID spans
    page_regex: re.Pattern = re.compile(r"<span id=\"page_\d+\"></span>")
    if page_regex.search(markdown):
        markdown = re.sub(page_regex,"", markdown)

    head_regex = re.compile(r"(?:# .+\n\n)?<div class=\"class_.+>\n\n(\d+)\n\n# (.+)\n\n</div>")
    if head_regex.search(markdown):
        markdown = re.sub(head_regex, f"# Chapter {chapter_number}: {chapter_title}", markdown)

    rule_html_block = (
        "<div class=\"class_sfp\">\n\n"
        "<div class=\"class_sfj\">\n\n"
        "<img src=\"rule.svg\" class=\"class_sfg\" />\n\n"
        "</div>\n\n"
        "</div>"
    )
    rule_html_replacement = (
        "<div style=\"width:75%;margin:auto;\">\n"
        "<img src=\"rule.svg\" alt=\"\" />\n"
        "</div>"
    )
    if rule_html_block in markdown:
        markdown = markdown.replace(rule_html_block, rule_html_replacement)

    parts = markdown.split("\n\n")
    if len(parts) > 1:
        markdown = "\n\n".join(part.replace("\n", " ") for part in parts)
    else:
        markdown = markdown.replace("\n", " ")

    bold_span_regex = re.compile(r"<span class=\"class_s6b4\">(.*?)\s*</span>")
    if bold_span_regex.search(markdown):
        markdown = bold_span_regex.sub(r"**\1** ", markdown)
    return markdown

def convert_chapters_to_markdown(
    stem: str,
    base_dir: Path = Path("static"),
) -> list[Path]:
    """Convert chapter HTML to markdown files under static/{stem}/markdown.

    Args:
        stem: EPUB stem used to locate toc.json and extracted files.
        base_dir: Base directory containing per-book folders.
    Returns:
        List of written markdown file paths.
    """
    book_dir = base_dir / stem
    toc_path = book_dir / "json" / "toc.json"
    if not toc_path.exists():
        raise FileNotFoundError(f"toc.json not found: {toc_path}")

    extracted_root = book_dir / "extracted"
    if not extracted_root.exists():
        raise FileNotFoundError(f"Extracted directory not found: {extracted_root}")

    markdown_root = book_dir / "markdown"
    markdown_root.mkdir(parents=True, exist_ok=True)
    audio_root = book_dir / "audio"

    rule_svg_path = markdown_root / "rule.svg"
    if not rule_svg_path.exists():
        rule_svg_path.write_text(RULE_SVG, encoding="utf-8")

    toc_entries: list[dict[str, Any]] = json.loads(
        toc_path.read_text(encoding="utf-8")
    )
    written: list[Path] = []
    toc_updated = False

    convert_md_task = progress.add_task(
        "Converting chapters to markdown",
        total=len(toc_entries),
    )
    with progress:
        for entry in toc_entries:
            chapter_title = entry.get("chapter_title") or f"Chapter {entry.get('order')}"
            chapter_number = entry.get("chapter_number") or entry.get("order")
            chapter_path = _resolve_chapter_path(entry, extracted_root)
            if not chapter_path.exists():
                progress.console.log(f"Chapter path missing: {chapter_path}")
                progress.advance(convert_md_task)
                continue

            html_text = chapter_path.read_text(encoding="utf-8")
            markdown = _pandoc_html_to_markdown(html_text)
            markdown = markdown.replace("image_rsrc6C6.jpg", "rule.svg")
            markdown = _postprocess_markdown(markdown, str(chapter_title), chapter_number)

            try:
                chapter_rel = chapter_path.relative_to(extracted_root)
            except ValueError:
                chapter_rel = Path(chapter_path.name)

            output_path = (markdown_root / chapter_rel).with_suffix(".md")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(f"{markdown}", encoding="utf-8")
            written.append(output_path)
            entry["markdown"] = output_path.as_posix()
            chapter_label = entry.get("chapter_number") or entry.get("order")
            if chapter_label is not None:
                title_for_audio = str(chapter_title).strip() if chapter_title else f"Chapter {chapter_label}"
                audio_name = f"{chapter_label}. {title_for_audio}"
                entry["audio"] = (audio_root / f"{audio_name}.m4a").as_posix()
            toc_updated = True
            progress.advance(convert_md_task)

    logger.info( # type: ignore
        "Converted {count} chapters to markdown in {path}",
        count=len(written),
        path=markdown_root,
    )
    if toc_updated:
        toc_path.write_text(
            json.dumps(toc_entries, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return written


if __name__ == "__main__":
    convert_chapters_to_markdown("defiance_of_the_fall_06")
