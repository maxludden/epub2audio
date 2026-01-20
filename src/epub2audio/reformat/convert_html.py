"""Convert extracted EPUB chapters into standalone HTML files."""

from __future__ import annotations

import json
import re
# import shutil
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from epub2audio.utils.logging import get_logger, get_progress

logger = get_logger()
progress = get_progress()
RULE_SVG="""<?xml version="1.0" encoding="UTF-8"?>
<svg id="Layer_1" data-name="Layer 1" xmlns="http://www.w3.org/2000/svg" \
xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1943.76 432.28">
  <defs>
    <style>
      .cls-1 {
        fill: url(#linear-gradient-2);
      }

      .cls-2 {
        fill: url(#linear-gradient);
      }
    </style>
    <linearGradient id="linear-gradient" x1="0" y1="200.58" x2="1943.76" \
y2="200.58" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#000" stop-opacity="0"/>
      <stop offset=".25" stop-color="#000" stop-opacity=".5"/>
      <stop offset=".5" stop-color="#000"/>
      <stop offset=".75" stop-color="#000" stop-opacity=".25"/>
      <stop offset="1" stop-color="#000" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="linear-gradient-2" x1="0" y1="222.42" x2="1943.76" \
y2="222.42" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff" stop-opacity="0" />
      <stop offset=".25" stop-color="#fff" stop-opacity=".5" />
      <stop offset=".5" stop-color="#fff" />
      <stop offset=".75" stop-color="#fff" stop-opacity=".25" />
      <stop offset="1" stop-color="#fff" stop-opacity="0" />
    </linearGradient>
  </defs>
  <rect class="cls-2" y="190" width="1943.76" height="20"/>
  <rect class="cls-1" y="210" width="1943.76" height="20"/>
</svg>
"""


def _resolve_chapter_path(
    entry: dict[str, Any],
    extracted_root: Path,
) -> Path:
    """Resolve chapter path from a TOC entry to an absolute filesystem path."""
    chapter_path = Path(entry.get("chapter_path", ""))
    if not chapter_path.is_absolute():
        chapter_path = Path.cwd() / extracted_root / chapter_path
    return chapter_path


def _parse_css_rules(css_text: str) -> dict[str, str]:
    """Parse class selectors and their declarations from CSS text."""
    rules: dict[str, str] = {}
    for match in re.finditer(r"([^{}]+)\{([^}]*)\}", css_text):
        selector_group = match.group(1)
        declarations = " ".join(match.group(2).split())
        for selector in selector_group.split(","):
            for class_match in re.finditer(r"\.([A-Za-z0-9_-]+)", selector):
                class_name = class_match.group(1)
                rules[class_name] = declarations
    return rules


def _parse_css_value(declarations: str, prop: str) -> str | None:
    pattern = re.compile(rf"{re.escape(prop)}\s*:\s*([^;]+)", re.IGNORECASE)
    found = pattern.search(declarations)
    return found.group(1).strip() if found else None


def _class_name_from_declarations(declarations: str) -> str:
    """Generate a human-readable class name from a CSS declaration block."""
    font_size = _parse_css_value(declarations, "font-size")
    font_weight = _parse_css_value(declarations, "font-weight")
    font_style = _parse_css_value(declarations, "font-style")
    text_align = _parse_css_value(declarations, "text-align")
    text_transform = _parse_css_value(declarations, "text-transform")

    name_parts: list[str] = []
    if font_size:
        size_token = font_size.replace(" ", "").replace("%", "pct")
        name_parts.append(size_token)
    if font_weight and any(token in font_weight for token in ["bold", "700", "800", "900"]):
        name_parts.append("bold")
    if font_style and "italic" in font_style:
        name_parts.append("italic")
    if text_align in {"center", "right", "left", "justify"}:
        name_parts.append(text_align)
    if text_transform in {"uppercase", "lowercase", "capitalize"}:
        name_parts.append(text_transform)

    base = "text"
    if font_size:
        size_num = re.findall(r"[\d.]+", font_size)
        if size_num:
            value = float(size_num[0])
            if ("px" in font_size and value >= 18) or ("em" in font_size and value >= 1.2):
                base = "heading"
    return "-".join([base] + name_parts) if name_parts else base


def _build_class_mapping(css_paths: list[Path]) -> dict[str, str]:
    """Build a mapping of original class names to generated human-readable names."""
    class_to_decls: dict[str, str] = {}
    for css_path in css_paths:
        css_text = css_path.read_text(encoding="utf-8")
        class_to_decls.update(_parse_css_rules(css_text))

    mapping: dict[str, str] = {}
    used: dict[str, int] = {}
    for class_name in sorted(class_to_decls):
        generated = _class_name_from_declarations(class_to_decls[class_name])
        count = used.get(generated, 0) + 1
        used[generated] = count
        mapping[class_name] = f"{generated}-{count}" if count > 1 else generated
    return mapping


def _replace_classes_in_html(html_text: str, mapping: dict[str, str]) -> str:
    """Replace class names in HTML text using a mapping."""
    def replace_match(match: re.Match[str]) -> str:
        classes = match.group(1).split()
        new_classes = [mapping.get(cls, cls) for cls in classes]
        return f'class="{" ".join(new_classes)}"'

    return re.sub(r'class="([^"]+)"', replace_match, html_text)


def _replace_classes_in_css(css_text: str, mapping: dict[str, str]) -> str:
    """Replace class selectors in CSS text using a mapping."""
    if not mapping:
        return css_text
    pattern = re.compile(
        r"\.([A-Za-z0-9_-]+)"
    )

    def repl(match: re.Match[str]) -> str:
        class_name = match.group(1)
        return f".{mapping.get(class_name, class_name)}"

    return pattern.sub(repl, css_text)


def _get_namespace(tag: str) -> str:
    """Return the XML namespace portion of a tag, or empty string if absent."""
    logger.trace(f"Entered _get_namespace({tag=})...")
    if tag.startswith("{") and "}" in tag:
        namespace = tag.split("}")[0].strip("{")
        logger.trace(f"{namespace=}")
        return namespace
    return ""


def _extract_stylesheet_hrefs(html_text: str) -> list[str]:
    """Return stylesheet hrefs from the document head.

    Args:
        html_text: Raw XHTML/HTML source.
    Returns:
        List of stylesheet href values in source order.
    """
    logger.trace(f"Entered _extract_stylesheet_hrefs(\nhtml_text='{html_text[:50]}')...")
    try:
        root = ET.fromstring(html_text)
    except ET.ParseError:
        return []
    ns = _get_namespace(root.tag)

    def q(tag: str) -> str:
        return f"{{{ns}}}{tag}" if ns else tag

    head = root.find(q("head")) or root.find(f".//{q('head')}")
    if head is None:
        return []

    hrefs: list[str] = []
    for link in head.findall(q("link")):
        rel = link.attrib.get("rel", "").lower()
        href = link.attrib.get("href")
        if rel == "stylesheet" and href:
            hrefs.append(href)
    logger.trace(
        f"Extracted stylesheets: {' ,'.join([stylesheet for stylesheet in hrefs])}"
    )
    return hrefs


def _replace_title(html_text: str, title: str) -> str:
    """Replace the <title> tag contents with the provided title.

    Args:
        html_text: Raw XHTML/HTML source.
        title: New document title text.
    Returns:
        Updated HTML string (or original if no <title> is found).
    """
    # Minimal HTML escaping to prevent malformed title text.
    logger.trace(f"Entered _replace_title({title=})")
    safe_title = (
        title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    pattern = re.compile(r"(<title>)(.*?)(</title>)", re.IGNORECASE | re.DOTALL)
    if pattern.search(html_text):
        return pattern.sub(rf"\1{safe_title}\3", html_text, count=1)
    return html_text


def _replace_image_src(html_text: str, original: str, replacement: str) -> str:
    """Replace an image src value with a new value."""
    logger.trace(f"Entered _replace_image_src({original=}, {replacement=})")
    return html_text.replace(f'src="{original}"', f'src="{replacement}"')


def copy_chapters_from_toc(
    stem: str,
    base_dir: Path = Path("static"),
) -> list[Path]:
    """Copy chapters listed in toc.json into static/{stem}/html.

    Keeps stylesheet links by copying linked CSS files and updates each HTML
    <title> tag to match the chapter title.

    Args:
        stem: EPUB stem used to locate toc.json and extracted files.
        base_dir: Base directory containing per-book folders.
    Returns:
        List of written HTML file paths.
    """
    logger.trace(f"Entered copy_chapter_from_toc({stem=}, {base_dir=})")
    book_dir = base_dir / stem
    toc_path = book_dir / "json" / "toc.json"
    if not toc_path.exists():
        raise FileNotFoundError(f"toc.json not found: {toc_path}")

    extracted_root = book_dir / "extracted"
    if not extracted_root.exists():
        raise FileNotFoundError(f"Extracted directory not found: {extracted_root}")

    html_root = book_dir / "html"
    html_root.mkdir(parents=True, exist_ok=True)

    # Ensure rule.svg is present for image replacements.
    rule_svg = html_root / "rule.svg"
    if not rule_svg.exists():
        rule_svg.write_text(
            RULE_SVG,
            encoding="utf-8",
        )

    # Load TOC entries that include chapter_path and chapter_title.
    toc_entries: list[dict[str, Any]] = json.loads(
        toc_path.read_text(encoding="utf-8")
    )
    written: list[Path] = []

    css_paths = list(extracted_root.rglob("*.css"))
    class_mapping = _build_class_mapping(css_paths)

    with progress:
        copy_task = progress.add_task("Copying chapters...", total=len(toc_entries))
        for entry in toc_entries:
            chapter_title = entry.get("chapter_title") or f"Chapter {entry.get('order')}"
            chapter_path = _resolve_chapter_path(entry, extracted_root)
            if not chapter_path.exists():
                logger.warning("Chapter path missing: {path}", path=chapter_path)
                continue

            try:
                chapter_rel = chapter_path.relative_to(extracted_root)
            except ValueError:
                chapter_rel = Path(chapter_path.name)

            output_path = html_root / chapter_rel
            output_path.parent.mkdir(parents=True, exist_ok=True)
            progress.update(copy_task, advance=.2, description=f"Copying to {output_path}...")

            # Update title while preserving the rest of the markup and links.
            html_text = chapter_path.read_text(encoding="utf-8")
            progress.update(copy_task, advance=.2, description="Read html_text...")
            updated_text = _replace_title(html_text, str(chapter_title))
            progress.update(copy_task, advance=.1, description="Replacing title...")
            updated_text = _replace_image_src(updated_text, "image_rsrc6C6.jpg", "rule.svg")
            progress.update(copy_task, advance=.1, description="Replacing hr image...")
            if class_mapping:
                updated_text = _replace_classes_in_html(updated_text, class_mapping)
            output_path.write_text(updated_text, encoding="utf-8")
            progress.update(copy_task, advance=.2, description="Writing updated \
html to {output_path}...")
            entry["html"] = str(output_path)
            progress.update(copy_task, advance=.2, description="Updating TOC...")
            written.append(output_path)

            for href in _extract_stylesheet_hrefs(html_text):
                if href.startswith(("http://", "https://", "data:", "mailto:")):
                    continue
                # Copy linked stylesheet to keep relative links valid.
                src_css = (chapter_path.parent / href).resolve()
                if not src_css.exists():
                    logger.warning("Stylesheet missing: {path}", path=src_css)
                    continue
                try:
                    css_rel = src_css.relative_to(extracted_root)
                except ValueError:
                    css_rel = Path(src_css.name)
                dst_css = html_root / css_rel
                dst_css.parent.mkdir(parents=True, exist_ok=True)
                if not dst_css.exists():
                    css_text = src_css.read_text(encoding="utf-8")
                    if class_mapping:
                        css_text = _replace_classes_in_css(css_text, class_mapping)
                    dst_css.write_text(css_text, encoding="utf-8")

    logger.trace("Copied {count} chapters to {path}", count=len(written), path=html_root)
    toc_path.write_text(json.dumps(toc_entries, indent=2), encoding="utf-8")
    return written


if __name__ == "__main__":
    copy_chapters_from_toc("defiance_of_the_fall_06")
