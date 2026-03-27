"""Library manager for books, settings, and download history."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
LIBRARY_DIR = BASE_DIR / "library"
LIBRARY_DIR.mkdir(exist_ok=True)

METADATA_FILE = LIBRARY_DIR / "_metadata.json"
SETTINGS_FILE = LIBRARY_DIR / "_settings.json"
HISTORY_FILE = LIBRARY_DIR / "_history.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "preferred_format": "Any",
    "preferred_source": "All Sources",
    "device_subdir": "",
    "default_collection": "",
    "open_library_after_download": True,
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _normalise_book(entry: dict[str, Any]) -> dict[str, Any]:
    collections = entry.get("collections", [])
    if not isinstance(collections, list):
        collections = []
    subjects = entry.get("subjects", [])
    if not isinstance(subjects, list):
        subjects = []

    normalized = {
        "id": entry.get("id") or str(uuid.uuid4())[:8],
        "filename": entry.get("filename", ""),
        "title": entry.get("title", "Unknown"),
        "author": entry.get("author", ""),
        "format": entry.get("format", ""),
        "cover_url": entry.get("cover_url", ""),
        "source": entry.get("source", ""),
        "language": entry.get("language", ""),
        "year": entry.get("year", ""),
        "rating": float(entry.get("rating", 0.0) or 0.0),
        "ratings_count": int(entry.get("ratings_count", 0) or 0),
        "description": entry.get("description", ""),
        "subjects": [str(item).strip() for item in subjects if str(item).strip()],
        "favorite": bool(entry.get("favorite", False)),
        "collections": sorted({str(item).strip() for item in collections if str(item).strip()}),
        "notes": entry.get("notes", ""),
        "downloaded_at": entry.get("downloaded_at") or _now_iso(),
        "updated_at": entry.get("updated_at") or entry.get("downloaded_at") or _now_iso(),
    }
    return normalized


def _load_metadata() -> list[dict[str, Any]]:
    data = _read_json(METADATA_FILE, [])
    if not isinstance(data, list):
        return []
    normalized = [_normalise_book(item) for item in data if isinstance(item, dict)]
    if normalized != data:
        _write_json(METADATA_FILE, normalized)
    return normalized


def _save_metadata(data: list[dict[str, Any]]) -> None:
    normalized = [_normalise_book(item) for item in data]
    _write_json(METADATA_FILE, normalized)


def get_all_books() -> list[dict[str, Any]]:
    return _load_metadata()


def get_book(book_id: str) -> dict[str, Any] | None:
    return next((book for book in _load_metadata() if book.get("id") == book_id), None)


def search_books_in_library(
    query: str = "",
    favorites_only: bool = False,
    collection: str = "",
    fmt: str = "",
    source: str = "",
) -> list[dict[str, Any]]:
    query_norm = query.strip().lower()
    results = []
    for book in _load_metadata():
        haystack = " ".join(
            [
                book.get("title", ""),
                book.get("author", ""),
                book.get("description", ""),
                " ".join(book.get("subjects", [])),
                " ".join(book.get("collections", [])),
            ]
        ).lower()
        if query_norm and query_norm not in haystack:
            continue
        if favorites_only and not book.get("favorite"):
            continue
        if collection and collection not in book.get("collections", []):
            continue
        if fmt and book.get("format", "").lower() != fmt.lower():
            continue
        if source and book.get("source", "") != source:
            continue
        results.append(book)
    results.sort(key=lambda item: (item.get("favorite", False), item.get("downloaded_at", "")), reverse=True)
    return results


def add_to_library(
    filename: str,
    title: str,
    author: str,
    fmt: str,
    cover_url: str = "",
    source: str = "",
    *,
    language: str = "",
    year: str = "",
    rating: float = 0.0,
    ratings_count: int = 0,
    description: str = "",
    subjects: list[str] | None = None,
    favorite: bool = False,
    collections: list[str] | None = None,
) -> dict[str, Any]:
    metadata = _load_metadata()
    entry = _normalise_book(
        {
            "id": str(uuid.uuid4())[:8],
            "filename": filename,
            "title": title,
            "author": author,
            "format": fmt,
            "cover_url": cover_url,
            "source": source,
            "language": language,
            "year": year,
            "rating": rating,
            "ratings_count": ratings_count,
            "description": description,
            "subjects": subjects or [],
            "favorite": favorite,
            "collections": collections or [],
            "downloaded_at": _now_iso(),
            "updated_at": _now_iso(),
        }
    )
    metadata.append(entry)
    _save_metadata(metadata)
    return entry


def update_book(book_id: str, **changes: Any) -> dict[str, Any] | None:
    metadata = _load_metadata()
    updated: dict[str, Any] | None = None
    for idx, book in enumerate(metadata):
        if book.get("id") != book_id:
            continue
        merged = dict(book)
        merged.update(changes)
        merged["updated_at"] = _now_iso()
        updated = _normalise_book(merged)
        metadata[idx] = updated
        break
    if updated is not None:
        _save_metadata(metadata)
    return updated


def toggle_favorite(book_id: str) -> dict[str, Any] | None:
    book = get_book(book_id)
    if not book:
        return None
    return update_book(book_id, favorite=not book.get("favorite", False))


def set_book_collections(book_id: str, collections: list[str]) -> dict[str, Any] | None:
    cleaned = sorted({item.strip() for item in collections if item.strip()})
    return update_book(book_id, collections=cleaned)


def list_collections() -> list[str]:
    names: set[str] = set()
    for book in _load_metadata():
        names.update(book.get("collections", []))
    return sorted(names)


def remove_from_library(book_id: str) -> bool:
    metadata = _load_metadata()
    entry = next((item for item in metadata if item.get("id") == book_id), None)
    if not entry:
        return False
    metadata.remove(entry)
    file_path = LIBRARY_DIR / entry["filename"]
    if file_path.exists():
        file_path.unlink()
    _save_metadata(metadata)
    return True


def get_book_path(book_id: str) -> Path | None:
    book = get_book(book_id)
    if not book:
        return None
    path = LIBRARY_DIR / book["filename"]
    return path if path.exists() else None


def get_settings() -> dict[str, Any]:
    data = _read_json(SETTINGS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    merged = {**DEFAULT_SETTINGS, **data}
    if merged != data:
        _write_json(SETTINGS_FILE, merged)
    return merged


def update_settings(**changes: Any) -> dict[str, Any]:
    settings = get_settings()
    settings.update(changes)
    _write_json(SETTINGS_FILE, settings)
    return settings


def get_download_history(limit: int | None = None) -> list[dict[str, Any]]:
    data = _read_json(HISTORY_FILE, [])
    if not isinstance(data, list):
        return []
    data = [item for item in data if isinstance(item, dict)]
    data.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    if limit is not None:
        return data[:limit]
    return data


def record_download_history(
    *,
    title: str,
    author: str,
    source: str,
    fmt: str,
    status: str,
    filename: str = "",
    message: str = "",
) -> dict[str, Any]:
    history = get_download_history()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": _now_iso(),
        "title": title,
        "author": author,
        "source": source,
        "format": fmt,
        "status": status,
        "filename": filename,
        "message": message,
    }
    history.insert(0, entry)
    _write_json(HISTORY_FILE, history[:500])
    return entry
