"""Run the full EPUB reformat + conversion pipeline."""

from __future__ import annotations

from pathlib import Path

from epub2audio.reformat.convert_html import convert_to_html
from epub2audio.reformat.convert_markdown import convert_to_markdown
from epub2audio.reformat.extract import generate_toc
from epub2audio.reformat.reformat import reformat_epub, unzip_epub_zip
from epub2audio.utils.logging import get_logger, get_progress

logger = get_logger()
progress = get_progress()


def main(
    epub: str | Path,
    *,
    base_dir: Path = Path("static"),
    copy_to_epub_dir: bool = True,
    slugify_stem: bool = True,
    unzip_overwrite: bool = True,
) -> list[Path]:
    """Run reformat, extract, HTML conversion, and markdown conversion."""
    with progress:
        convert_task = progress.add_task("convert_epub", total=5)
        zip_path = reformat_epub(
            epub,
            base_dir=base_dir,
            copy_to_epub_dir=copy_to_epub_dir,
            slugify_stem=slugify_stem,
        )
        progress.update(convert_task, advance=1, description="extract zip archive")
        extracted_root = unzip_epub_zip(
            zip_path,
            overwrite=unzip_overwrite,
        )
        progress.update(convert_task, advance=1, description="create chapters from TOC")
        generate_toc(extracted_root)
        stem = extracted_root.parent.name
        progress.update(
            convert_task, advance=1, description="convert chapters from HTML"
        )
        convert_to_html(
            stem,
            base_dir=base_dir,
        )
        progress.update(
            convert_task, advance=1, description="converting chapter to Markdown"
        )
        markdown_paths = convert_to_markdown(
            stem,
            base_dir=base_dir,
        )
        progress.update(
            convert_task, advance=1, description="Finished converting to markdown."
        )
        logger.info("Completed pipeline for {epub}", epub=epub)
    return markdown_paths


if __name__ == "__main__":
    # if len(sys.argv) < 2:
    #     raise SystemExit("Usage: python -m epub2audio.reformat.reformat_main <file.epub>")
    main(
        "/Users/maxludden/dev/py/epub2audio/static/defiance_of_the_fall_06/epub/defiance_of_the_fall_06.epub"
    )
