"""Format epub ebooks into zip archives."""

from pathlib import Path
from shutil import copy2
from slugify import slugify

def change_ext(
    epub: str,
    copy_epub: bool = True,
    base_dir: Path = Path('static'),
    slugify_stem: bool = True) -> str:
    """Change the extension of and epub ebook to .zip archive.
    Args:
        epub(str): The ebook to change the extension of.
        slugify(bool): Whether to slugify the epub filename.
    Returns:
        str: The string of the file path of the zip archive created.
    Raises:
        FileNotFoundError: The epub file does not exist.
    """
    epub_path = Path(epub)

    if not epub_path.exists():
        raise FileNotFoundError(f"Invalid input: {epub_path=}")

    epub_stem: str = slugify(epub_path.stem) if slugify_stem else epub_path.stem
    book_dir = base_dir / epub_stem
    epub_dir = book_dir / "epub"
    zip_dir = book_dir / "zip"

    if copy_epub:
        if not epub_dir.exists():
            epub_dir.mkdir(parents=True, exist_ok=True)
        copy2(src=epub_path, dst=epub_dir / f'{epub_stem}.epub')

    if not zip_dir.exists():
        zip_dir.mkdir(parents=True, exist_ok=True)

    zip_path: Path = zip_dir / f'{epub_stem}.zip'
    copy2(src=epub_path, dst=zip_path)
    return str(zip_path)
