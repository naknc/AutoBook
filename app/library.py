"""Library manager – metadata and file storage for downloaded books."""

import json
import uuid
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
LIBRARY_DIR = BASE_DIR / "library"
LIBRARY_DIR.mkdir(exist_ok=True)
METADATA_FILE = LIBRARY_DIR / "_metadata.json"


def _load_metadata() -> list[dict[str, Any]]:
    if METADATA_FILE.exists():
        try:
            return json.loads(METADATA_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def _save_metadata(data: list[dict[str, Any]]) -> None:
    METADATA_FILE.write_text(json.dumps(data, indent=2))


def get_all_books() -> list[dict[str, Any]]:
    return _load_metadata()


def add_to_library(
    filename: str,
    title: str,
    author: str,
    fmt: str,
    cover_url: str = "",
    source: str = "",
) -> dict[str, Any]:
    meta = _load_metadata()
    entry: dict[str, Any] = {
        "id": str(uuid.uuid4())[:8],
        "filename": filename,
        "title": title,
        "author": author,
        "format": fmt,
        "cover_url": cover_url,
        "source": source,
    }
    meta.append(entry)
    _save_metadata(meta)
    return entry


def remove_from_library(book_id: str) -> bool:
    meta = _load_metadata()
    entry = next((m for m in meta if m.get("id") == book_id), None)
    if not entry:
        return False
    meta.remove(entry)
    fp = LIBRARY_DIR / entry["filename"]
    if fp.exists():
        fp.unlink()
    _save_metadata(meta)
    return True


def get_book_path(book_id: str) -> Path | None:
    meta = _load_metadata()
    book = next((m for m in meta if m["id"] == book_id), None)
    if book:
        p = LIBRARY_DIR / book["filename"]
        if p.exists():
            return p
    return None
