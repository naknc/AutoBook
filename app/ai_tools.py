"""Optional AI helpers for summary and classification."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import request

from app.library import get_book, update_book
from app.logging_utils import log_exception


def ai_is_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def _call_openai(prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": prompt,
    }
    req = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=45) as response:
        data = json.loads(response.read().decode("utf-8"))
    text_parts: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text_parts.append(content.get("text", ""))
    return "\n".join(part for part in text_parts if part).strip()


def ai_enrich_book(book_id: str) -> dict[str, Any]:
    book = get_book(book_id)
    if not book:
        raise ValueError("Book could not be found.")
    prompt = (
        "You are enriching metadata for a library app. "
        "Return compact JSON with keys summary and categories. "
        "summary must be one concise sentence. categories must be a short list of 2 or 3 English labels.\n\n"
        f"Title: {book.get('title', '')}\n"
        f"Author: {book.get('author', '')}\n"
        f"Description: {book.get('description', '')}\n"
        f"Subjects: {', '.join(book.get('subjects', []))}\n"
        f"Notes: {book.get('notes', '')[:500]}\n"
    )
    try:
        raw = _call_openai(prompt)
        data = json.loads(raw)
        summary = str(data.get("summary", "")).strip()
        categories = [str(item).strip() for item in data.get("categories", []) if str(item).strip()][:3]
        update_book(book_id, summary=summary or book.get("summary", ""), auto_categories=categories or book.get("auto_categories", []))
        return {"summary": summary, "categories": categories}
    except Exception:
        log_exception(f"AI enrichment failed for book_id={book_id!r}")
        raise


def ai_generate_search_suggestions(query: str) -> list[str]:
    if not query.strip():
        return []
    if not ai_is_configured():
        return []
    prompt = (
        "Generate 5 short alternative search queries for a book discovery app. "
        "Return only JSON array of strings.\n\n"
        f"Query: {query.strip()}"
    )
    try:
        raw = _call_openai(prompt)
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [str(item).strip() for item in data if str(item).strip()][:5]
    except Exception:
        log_exception(f"AI search suggestion failed for query={query!r}")
        return []


def ai_generate_tags(book_id: str) -> dict[str, Any]:
    book = get_book(book_id)
    if not book:
        raise ValueError("Book could not be found.")
    prompt = (
        "Return compact JSON with key tags for a library app. "
        "tags must be 4 to 6 short lowercase tags.\n\n"
        f"Title: {book.get('title', '')}\n"
        f"Author: {book.get('author', '')}\n"
        f"Description: {book.get('description', '')}\n"
        f"Subjects: {', '.join(book.get('subjects', []))}\n"
    )
    try:
        raw = _call_openai(prompt)
        data = json.loads(raw)
        tags = [str(item).strip().lower() for item in data.get("tags", []) if str(item).strip()][:6]
        update_book(book_id, tags=tags or book.get("tags", []))
        return {"tags": tags}
    except Exception:
        log_exception(f"AI tag generation failed for book_id={book_id!r}")
        raise
