"""Library manager for books, settings, and download history."""

from __future__ import annotations

import json
import hashlib
import shutil
import zipfile
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
LIBRARY_DIR = BASE_DIR / "library"
LIBRARY_DIR.mkdir(exist_ok=True)

METADATA_FILE = LIBRARY_DIR / "_metadata.json"
SETTINGS_FILE = LIBRARY_DIR / "_settings.json"
HISTORY_FILE = LIBRARY_DIR / "_history.json"
TRANSFER_HISTORY_FILE = LIBRARY_DIR / "_transfer_history.json"
USAGE_FILE = LIBRARY_DIR / "_usage.json"
QUEUE_FILE = LIBRARY_DIR / "_download_queue.json"
SEARCH_CACHE_DIR = LIBRARY_DIR / "search_cache"
COMPANION_DIR = LIBRARY_DIR / "companion"
PLUGINS_DIR = BASE_DIR / "plugins"
EXPORT_DIR = LIBRARY_DIR / "exports"
EXPORT_DIR.mkdir(exist_ok=True)
SEARCH_CACHE_DIR.mkdir(exist_ok=True)
COMPANION_DIR.mkdir(exist_ok=True)
PLUGINS_DIR.mkdir(exist_ok=True)

DEFAULT_SETTINGS: dict[str, Any] = {
    "preferred_format": "Any",
    "preferred_source": "All Sources",
    "device_subdir": "",
    "default_collection": "",
    "open_library_after_download": True,
    "library_view": "List",
    "auto_organize_by": "None",
    "theme_preset": "Corporate Blue",
    "notifications_enabled": True,
    "allowed_sources": ["Project Gutenberg", "Open Library", "External"],
    "telemetry_enabled": True,
    "interface_language": "English",
    "allowed_formats": ["EPUB", "PDF"],
    "search_cache_enabled": True,
    "search_cache_max_age_hours": 72,
    "queue_autostart": True,
    "active_device_profile": "Default",
    "device_profiles": [{"name": "Default", "subdir": "", "kind": "Generic"}],
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


def _smart_summary(title: str, author: str, description: str) -> str:
    text = " ".join(description.replace("\n", " ").split()).strip()
    if not text:
        base = title.strip() or "Untitled"
        creator = author.strip()
        return f"{base} by {creator}." if creator else base
    trimmed = text[:260].strip()
    if len(text) > 260:
        cut = max(trimmed.rfind(". "), trimmed.rfind("; "), trimmed.rfind(", "))
        trimmed = trimmed[:cut].strip() if cut > 120 else trimmed.rstrip(" ,;:")
        trimmed = f"{trimmed}..."
    return trimmed


def _auto_categories(title: str, description: str, subjects: list[str], tags: list[str]) -> list[str]:
    haystack = " ".join([title, description, " ".join(subjects), " ".join(tags)]).lower()
    rules = [
        ("Politics", ["politic", "state", "government", "revolution", "war", "ideolog"]),
        ("Philosophy", ["philosoph", "ethic", "metaphys", "exist", "reason"]),
        ("Science Fiction", ["science fiction", "dystopia", "future", "space", "robot"]),
        ("Fantasy", ["fantasy", "myth", "dragon", "magic", "legend"]),
        ("Business", ["business", "management", "finance", "leadership", "strategy"]),
        ("History", ["history", "histor", "ancient", "empire", "civilization"]),
        ("Essays", ["essay", "criticism", "articles", "collection of essays"]),
        ("Children", ["children", "child", "young reader", "fairy tale"]),
        ("Classics", ["classic", "novel", "public domain", "literature"]),
    ]
    categories = [label for label, keywords in rules if any(keyword in haystack for keyword in keywords)]
    if not categories and subjects:
        categories = [subject.strip().title() for subject in subjects[:3] if subject.strip()]
    if not categories:
        categories = ["General"]
    return categories[:3]


def _normalise_book(entry: dict[str, Any]) -> dict[str, Any]:
    collections = entry.get("collections", [])
    if not isinstance(collections, list):
        collections = []
    subjects = entry.get("subjects", [])
    if not isinstance(subjects, list):
        subjects = []
    tags = entry.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    summary = entry.get("summary", "")
    if not isinstance(summary, str):
        summary = ""
    auto_categories = entry.get("auto_categories", [])
    if not isinstance(auto_categories, list):
        auto_categories = []

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
        "summary": summary.strip() or _smart_summary(entry.get("title", "Unknown"), entry.get("author", ""), entry.get("description", "")),
        "subjects": [str(item).strip() for item in subjects if str(item).strip()],
        "auto_categories": [str(item).strip() for item in (auto_categories or _auto_categories(entry.get("title", "Unknown"), entry.get("description", ""), subjects, tags)) if str(item).strip()][:3],
        "favorite": bool(entry.get("favorite", False)),
        "collections": sorted({str(item).strip() for item in collections if str(item).strip()}),
        "notes": entry.get("notes", ""),
        "reading_status": entry.get("reading_status", "Unread"),
        "tags": sorted({str(item).strip() for item in tags if str(item).strip()}),
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
                book.get("notes", ""),
                " ".join(book.get("subjects", [])),
                " ".join(book.get("collections", [])),
                " ".join(book.get("tags", [])),
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
    reading_status: str = "Unread",
    tags: list[str] | None = None,
    notes: str = "",
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
            "reading_status": reading_status,
            "tags": tags or [],
            "notes": notes,
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


def list_tags() -> list[str]:
    names: set[str] = set()
    for book in _load_metadata():
        names.update(book.get("tags", []))
    return sorted(names)


def set_reading_status(book_id: str, status: str) -> dict[str, Any] | None:
    return update_book(book_id, reading_status=status)


def set_book_notes_and_tags(book_id: str, notes: str, tags: list[str]) -> dict[str, Any] | None:
    cleaned_tags = sorted({item.strip() for item in tags if item.strip()})
    return update_book(book_id, notes=notes, tags=cleaned_tags)


def apply_bulk_update(
    book_ids: list[str],
    *,
    favorite: bool | None = None,
    collection: str | None = None,
    reading_status: str | None = None,
) -> int:
    updated_count = 0
    metadata = _load_metadata()
    target_ids = set(book_ids)
    for idx, book in enumerate(metadata):
        if book.get("id") not in target_ids:
            continue
        merged = dict(book)
        if favorite is not None:
            merged["favorite"] = favorite
        if collection:
            merged["collections"] = sorted({*merged.get("collections", []), collection})
        if reading_status:
            merged["reading_status"] = reading_status
        merged["updated_at"] = _now_iso()
        metadata[idx] = _normalise_book(merged)
        updated_count += 1
    if updated_count:
        _save_metadata(metadata)
    return updated_count


def delete_books(book_ids: list[str]) -> int:
    removed = 0
    for book_id in book_ids:
        if remove_from_library(book_id):
            removed += 1
    return removed


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


def record_usage_event(event: str, **details: Any) -> dict[str, Any]:
    history = _read_json(USAGE_FILE, [])
    if not isinstance(history, list):
        history = []
    entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": _now_iso(),
        "event": event,
        "details": {key: value for key, value in details.items()},
    }
    history.insert(0, entry)
    _write_json(USAGE_FILE, history[:1000])
    return entry


def get_usage_events(limit: int | None = None) -> list[dict[str, Any]]:
    data = _read_json(USAGE_FILE, [])
    if not isinstance(data, list):
        return []
    events = [item for item in data if isinstance(item, dict)]
    events.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return events[:limit] if limit is not None else events


def _cache_path_for_query(query: str) -> Path:
    digest = hashlib.sha1(query.strip().lower().encode("utf-8")).hexdigest()[:16]
    return SEARCH_CACHE_DIR / f"{digest}.json"


def load_search_cache(query: str, max_age_hours: int = 72) -> list[dict[str, Any]]:
    path = _cache_path_for_query(query)
    payload = _read_json(path, {})
    if not isinstance(payload, dict):
        return []
    timestamp = payload.get("cached_at", "")
    try:
        cached_at = datetime.fromisoformat(timestamp)
    except Exception:
        return []
    age = datetime.now() - cached_at
    if age.total_seconds() > max_age_hours * 3600:
        return []
    results = payload.get("results", [])
    return results if isinstance(results, list) else []


def save_search_cache(query: str, results: list[dict[str, Any]]) -> Path:
    path = _cache_path_for_query(query)
    _write_json(path, {"cached_at": _now_iso(), "query": query, "results": results})
    return path


def get_download_queue() -> list[dict[str, Any]]:
    data = _read_json(QUEUE_FILE, [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def enqueue_download_job(payload: dict[str, Any]) -> dict[str, Any]:
    queue = get_download_queue()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "status": "queued",
        **payload,
    }
    queue.append(entry)
    _write_json(QUEUE_FILE, queue)
    return entry


def update_download_job(job_id: str, **changes: Any) -> dict[str, Any] | None:
    queue = get_download_queue()
    for idx, item in enumerate(queue):
        if item.get("id") != job_id:
            continue
        merged = dict(item)
        merged.update(changes)
        merged["updated_at"] = _now_iso()
        queue[idx] = merged
        _write_json(QUEUE_FILE, queue)
        return merged
    return None


def get_next_queued_job() -> dict[str, Any] | None:
    for item in get_download_queue():
        if item.get("status") == "queued":
            return item
    return None


def clear_finished_queue_jobs() -> int:
    queue = get_download_queue()
    kept = [item for item in queue if item.get("status") not in {"success", "failed", "cancelled"}]
    removed = len(queue) - len(kept)
    if removed:
        _write_json(QUEUE_FILE, kept)
    return removed


def cancel_download_job(job_id: str) -> dict[str, Any] | None:
    return update_download_job(job_id, status="cancelled")


def retry_download_job(job_id: str) -> dict[str, Any] | None:
    return update_download_job(job_id, status="queued", message="")


def reorder_download_job(job_id: str, direction: str) -> list[dict[str, Any]]:
    queue = get_download_queue()
    index = next((idx for idx, item in enumerate(queue) if item.get("id") == job_id), None)
    if index is None:
        return queue
    if direction == "up" and index > 0:
        queue[index - 1], queue[index] = queue[index], queue[index - 1]
    elif direction == "down" and index < len(queue) - 1:
        queue[index + 1], queue[index] = queue[index], queue[index + 1]
    _write_json(QUEUE_FILE, queue)
    return queue


def get_search_cache_stats() -> dict[str, int]:
    files = list(SEARCH_CACHE_DIR.glob("*.json"))
    total_bytes = sum(path.stat().st_size for path in files if path.exists())
    return {"entries": len(files), "bytes": total_bytes}


def clear_search_cache() -> int:
    removed = 0
    for path in SEARCH_CACHE_DIR.glob("*.json"):
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def get_device_profiles() -> list[dict[str, str]]:
    profiles = get_settings().get("device_profiles", [])
    if not isinstance(profiles, list) or not profiles:
        profiles = [{"name": "Default", "subdir": "", "kind": "Generic"}]
    cleaned = []
    for item in profiles:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip() or "Profile"
        cleaned.append({"name": name, "subdir": str(item.get("subdir", "")).strip(), "kind": str(item.get("kind", "Generic")).strip() or "Generic"})
    return cleaned or [{"name": "Default", "subdir": "", "kind": "Generic"}]


def save_device_profile(name: str, subdir: str = "", kind: str = "Generic") -> list[dict[str, str]]:
    profiles = get_device_profiles()
    updated = False
    for profile in profiles:
        if profile["name"] == name:
            profile["subdir"] = subdir.strip()
            profile["kind"] = kind.strip() or "Generic"
            updated = True
            break
    if not updated:
        profiles.append({"name": name.strip() or "Profile", "subdir": subdir.strip(), "kind": kind.strip() or "Generic"})
    update_settings(device_profiles=profiles)
    return profiles


def delete_device_profile(name: str) -> list[dict[str, str]]:
    profiles = [profile for profile in get_device_profiles() if profile["name"] != name]
    if not profiles:
        profiles = [{"name": "Default", "subdir": "", "kind": "Generic"}]
    active = get_settings().get("active_device_profile", "Default")
    changes: dict[str, Any] = {"device_profiles": profiles}
    if active == name:
        changes["active_device_profile"] = profiles[0]["name"]
    update_settings(**changes)
    return profiles


def get_optional_tooling() -> dict[str, bool]:
    return {
        "tesseract": shutil.which("tesseract") is not None,
        "pandoc": shutil.which("pandoc") is not None,
        "ebook-convert": shutil.which("ebook-convert") is not None,
    }


def list_local_plugins() -> list[dict[str, str]]:
    plugins: list[dict[str, str]] = []
    for path in sorted(PLUGINS_DIR.glob("**/*.json")):
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            continue
        plugins.append(
            {
                "name": str(payload.get("name", path.stem)),
                "version": str(payload.get("version", "0.1.0")),
                "description": str(payload.get("description", "")),
                "path": str(path.relative_to(BASE_DIR)),
            }
        )
    return plugins


def generate_companion_feed() -> Path:
    books = _load_metadata()
    payload = {
        "generated_at": _now_iso(),
        "book_count": len(books),
        "books": [
            {
                "id": book.get("id", ""),
                "title": book.get("title", "Unknown"),
                "author": book.get("author", ""),
                "summary": book.get("summary", ""),
                "categories": book.get("auto_categories", []),
                "format": book.get("format", ""),
                "favorite": book.get("favorite", False),
            }
            for book in books
        ],
    }
    path = COMPANION_DIR / "library_feed.json"
    _write_json(path, payload)
    return path


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


def get_transfer_history(limit: int | None = None) -> list[dict[str, Any]]:
    data = _read_json(TRANSFER_HISTORY_FILE, [])
    if not isinstance(data, list):
        return []
    data = [item for item in data if isinstance(item, dict)]
    data.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    if limit is not None:
        return data[:limit]
    return data


def record_transfer_history(
    *,
    title: str,
    device_name: str,
    status: str,
    message: str = "",
) -> dict[str, Any]:
    history = get_transfer_history()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": _now_iso(),
        "title": title,
        "device_name": device_name,
        "status": status,
        "message": message,
    }
    history.insert(0, entry)
    _write_json(TRANSFER_HISTORY_FILE, history[:500])
    return entry


def get_recommendations(limit: int = 6) -> list[dict[str, Any]]:
    books = _load_metadata()
    if len(books) < 2:
        return []
    ranked: list[tuple[int, dict[str, Any]]] = []
    for book in books:
        score = 0
        score += 3 if book.get("favorite") else 0
        score += 2 if book.get("reading_status") == "Reading" else 0
        score += min(len(book.get("subjects", [])), 3)
        score += min(len(book.get("tags", [])), 2)
        ranked.append((score, book))
    ranked.sort(key=lambda item: (item[0], item[1].get("downloaded_at", "")), reverse=True)
    return [book for _, book in ranked[:limit]]


def get_library_analytics() -> dict[str, Any]:
    books = _load_metadata()
    by_source: dict[str, int] = {}
    by_format: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_language: dict[str, int] = {}
    by_category: Counter[str] = Counter()
    for book in books:
        by_source[book.get("source", "Unknown")] = by_source.get(book.get("source", "Unknown"), 0) + 1
        by_format[book.get("format", "").upper() or "Unknown"] = by_format.get(book.get("format", "").upper() or "Unknown", 0) + 1
        by_status[book.get("reading_status", "Unread")] = by_status.get(book.get("reading_status", "Unread"), 0) + 1
        by_language[book.get("language", "Unknown") or "Unknown"] = by_language.get(book.get("language", "Unknown") or "Unknown", 0) + 1
        by_category.update(book.get("auto_categories", []))
    usage_events = get_usage_events()
    event_counter = Counter(event.get("event", "unknown") for event in usage_events)
    recent_downloads = get_download_history(limit=100)
    trending_counter = Counter(
        f"{entry.get('title', 'Unknown')}|{entry.get('author', '')}"
        for entry in recent_downloads
        if entry.get("status") == "success"
    )
    trending_titles = []
    for key, count in trending_counter.most_common(5):
        title, author = key.split("|", 1)
        trending_titles.append({"title": title, "author": author, "count": count})
    return {
        "total_books": len(books),
        "favorites": sum(1 for book in books if book.get("favorite")),
        "collections": len(list_collections()),
        "tags": len(list_tags()),
        "by_source": dict(sorted(by_source.items(), key=lambda item: item[1], reverse=True)),
        "by_format": dict(sorted(by_format.items(), key=lambda item: item[1], reverse=True)),
        "by_status": dict(sorted(by_status.items(), key=lambda item: item[1], reverse=True)),
        "by_language": dict(sorted(by_language.items(), key=lambda item: item[1], reverse=True)),
        "by_category": dict(by_category.most_common()),
        "trending_titles": trending_titles,
        "usage_events": len(usage_events),
        "usage_by_event": dict(event_counter.most_common(6)),
    }


def export_library_snapshot() -> Path:
    payload = {
        "exported_at": _now_iso(),
        "settings": get_settings(),
        "books": _load_metadata(),
        "download_history": get_download_history(),
        "transfer_history": get_transfer_history(),
    }
    path = EXPORT_DIR / f"autobook_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    _write_json(path, payload)
    return path


def import_library_snapshot(path_str: str) -> dict[str, int]:
    payload = _read_json(Path(path_str), {})
    if not isinstance(payload, dict):
        raise ValueError("Import file is not a valid export payload.")

    incoming_books = payload.get("books", [])
    imported = 0
    skipped = 0
    existing = _load_metadata()
    existing_keys = {(book.get("title", "").lower(), book.get("author", "").lower(), book.get("filename", "").lower()) for book in existing}
    for entry in incoming_books if isinstance(incoming_books, list) else []:
        if not isinstance(entry, dict):
            continue
        key = (entry.get("title", "").lower(), entry.get("author", "").lower(), entry.get("filename", "").lower())
        if key in existing_keys:
            skipped += 1
            continue
        existing.append(_normalise_book(entry))
        existing_keys.add(key)
        imported += 1
    _save_metadata(existing)
    return {"imported": imported, "skipped": skipped}


def organize_library_files(mode: str = "None") -> int:
    if mode == "None":
        return 0
    metadata = _load_metadata()
    moved = 0
    for idx, book in enumerate(metadata):
        current_path = LIBRARY_DIR / book["filename"]
        if not current_path.exists():
            continue
        if mode == "Author":
            folder_name = book.get("author", "Unknown Author").strip() or "Unknown Author"
        elif mode == "Format":
            folder_name = book.get("format", "unknown").upper() or "UNKNOWN"
        else:
            folder_name = book.get("source", "Unknown Source").strip() or "Unknown Source"
        safe_folder = "".join(ch for ch in folder_name if ch.isalnum() or ch in " -_").strip() or "Misc"
        target_dir = LIBRARY_DIR / safe_folder
        target_dir.mkdir(exist_ok=True)
        target_path = target_dir / current_path.name
        if target_path == current_path:
            continue
        if target_path.exists():
            continue
        current_path.rename(target_path)
        metadata[idx]["filename"] = str(target_path.relative_to(LIBRARY_DIR))
        metadata[idx]["updated_at"] = _now_iso()
        moved += 1
    if moved:
        _save_metadata(metadata)
    return moved


def scan_library_health() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for book in _load_metadata():
        filename = book.get("filename", "")
        path = LIBRARY_DIR / filename
        status = "healthy"
        message = "File looks valid."
        if not path.exists():
            status = "missing"
            message = "File is missing from disk."
        elif path.suffix.lower() == ".epub":
            try:
                with zipfile.ZipFile(path, "r") as archive:
                    if "mimetype" not in archive.namelist():
                        status = "warning"
                        message = "EPUB archive is missing the mimetype entry."
            except Exception:
                status = "corrupt"
                message = "EPUB archive could not be opened."
        elif path.suffix.lower() == ".pdf":
            try:
                header = path.read_bytes()[:5]
                if header != b"%PDF-":
                    status = "warning"
                    message = "PDF header is not valid."
            except Exception:
                status = "corrupt"
                message = "PDF could not be read."
        results.append(
            {
                "id": book.get("id", ""),
                "title": book.get("title", "Unknown"),
                "filename": filename,
                "status": status,
                "message": message,
            }
        )
    return results
