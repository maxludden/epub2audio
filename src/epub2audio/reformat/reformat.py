"""Reformat ePub file into a zip archive."""

from __future__ import annotations

import shutil
from pathlib import Path
from zipfile import ZipFile

from slugify import slugify

from epub2audio.utils.logging import get_logger

logger = get_logger()


def reformat_epub(
    epub: str | Path,
    base_dir: Path = Path("static"),
    copy_to_epub_dir: bool = True,
    slugify_stem: bool = True,
) -> Path:
    """Reformat epub file as a zip archive.
    Args:
        epub(PathLike): The filepath of the epub to convert.
        base_dir(Path): Base directory for per-book storage. Defaults to `static`
        copy_to_epub_dir(bool): Copy the epub to the epub directory. Defaults \
            to `True`
        slugify_stem(bool): Whether to slugify the epub's stem.
    Returns:
        Path: the path of the reformatted epub's zip archive.
    """
    logger.trace(f"Entered reformat({epub}...")

    # Validate path
    epub_path: Path = epub if isinstance(epub, Path) else Path(epub)
    if not epub_path.exists():
        logger.error(f"Invalid input: {epub=}")
        raise FileNotFoundError(f"Invalid input: {epub=}")
    if epub_path.suffix != ".epub":
        logger.error(f"Invalid file extension: {epub_path.suffix=}")
        raise TypeError(f"Invalid file extension: {epub_path.suffix=}")

    # Epub stem
    epub_stem: str = epub_path.stem
    if slugify_stem:
        logger.trace("Slugifying ePub file's stem...")
        epub_stem = slugify(
            epub_stem,
            separator="_",
        )
    logger.trace(f"{epub_stem=}")

    book_dir = base_dir / epub_stem
    epub_dir_path = book_dir / "epub"
    zip_dir_path = book_dir / "zip"

    if copy_to_epub_dir:
        epub_dir_path = epub_dir_path.resolve()
        epub_path_resolved = epub_path.resolve()
        target_epub_path = epub_dir_path / f"{epub_stem}.epub"
        if epub_path_resolved == target_epub_path:
            logger.trace("ePub already in epub_dir...")
        else:
            logger.trace(f"Copying epub to {epub_dir_path}...")

            if not epub_dir_path.exists():
                logger.trace("`epub_dir` does not exist. Making it...")
                epub_dir_path.mkdir(parents=True, exist_ok=True)

            shutil.copy2(
                src=epub_path_resolved,
                dst=target_epub_path,
            )
            epub_path = target_epub_path
            logger.trace(f"New epub_path: {epub_path=}")

    logger.trace(f"Copying epub to {zip_dir_path} with .zip extension...")
    if not zip_dir_path.exists():
        logger.trace("`zip_dir` does not exist. Making it...")
        zip_dir_path.mkdir(parents=True, exist_ok=True)

    zip_path = zip_dir_path / f"{epub_stem}.zip"
    shutil.copy2(
        src=epub_path,
        dst=zip_path,
    )
    logger.trace(f"Created zip archive copy: {zip_path=}")
    return zip_path


def unzip_epub_zip(
    zip_path: Path,
    extracted_dir: Path | None = None,
    mkdir: bool = True,
    overwrite: bool = True,
) -> Path:
    """Unzip a .zip copy of an ePub into an extracted directory."""
    logger.trace(f"Entered unzip_epub_zip({zip_path}...)")

    if extracted_dir is None:
        if zip_path.parent.name == "zip":
            extracted_dir = zip_path.parent.parent / "extracted"
        else:
            extracted_dir = zip_path.parent / "extracted"
    extracted_dir_path = extracted_dir.resolve()
    target_dir = extracted_dir_path

    if mkdir and not extracted_dir_path.exists():
        logger.trace("`extracted_dir` does not exist. Making it...")
        extracted_dir_path.mkdir(parents=True, exist_ok=True)

    if target_dir.exists():
        if overwrite:
            logger.trace("Extracted directory exists; overwriting...")
            shutil.rmtree(target_dir)
        else:
            logger.trace(f"Extracted directory already exists: {target_dir=}")
            return target_dir

    target_dir.mkdir(parents=True, exist_ok=True)
    logger.trace(f"Extracting {zip_path} to {target_dir}...")
    with ZipFile(zip_path, "r") as zip_file:
        zip_file.extractall(target_dir)
    logger.trace(f"Extraction complete: {target_dir=}")
    return target_dir


if __name__ == "__main__":
    EPUB = "/Users/maxludden/dev/py/epub2audio/static/defiance_of_the_fall_06/epub/defiance_of_the_fall_06.epub"

    _zip_path: Path = reformat_epub(EPUB)
    unzip_epub_zip(_zip_path)
