"""
Book search engine – queries Project Gutenberg and Open Library / Internet
Archive, returning unified results for the UI.
"""

from __future__ import annotations

import os
import re
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from app.logging_utils import log_exception

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Thread-local sessions so each thread has its own connection pool
_thread_local = threading.local()


def _get_session() -> requests.Session:
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers["User-Agent"] = _UA
        _thread_local.session = s
    return _thread_local.session


TIMEOUT = 12  # seconds

# Limit concurrent archive.org requests so we don't get throttled
_IA_SEMAPHORE = threading.Semaphore(4)


# ── Data classes ────────────────────────────────────────────────────

@dataclass
class DownloadLink:
    url: str
    format: str
    mirror: str = ""


@dataclass
class BookResult:
    title: str
    author: str
    cover_url: str = ""
    year: str = ""
    source: str = ""
    language: str = ""
    rating: float = 0.0
    ratings_count: int = 0
    description: str = ""
    subjects: list[str] = field(default_factory=list)
    downloads: list[DownloadLink] = field(default_factory=list)


def _clean(text: str) -> str:
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", text).strip()


_GUTENBERG_LANG_RE = re.compile(r"\(([A-Za-z][A-Za-z0-9 ()-]+)\)\s*$")
_GUTENBERG_ALLOWED = {"english", "turkish"}


def _detect_gutenberg_lang(title: str) -> str:
    m = _GUTENBERG_LANG_RE.search(title)
    return m.group(1).strip() if m else "English"


def _search_gutenberg(query: str, max_results: int = 8) -> list[BookResult]:
    """Search Project Gutenberg via their simple search page."""
    results: list[BookResult] = []
    try:
        url = "https://www.gutenberg.org/ebooks/search/"
        params = {"query": query, "submit_search": "Go!"}
        resp = _get_session().get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for li in soup.select("li.booklink")[:max_results * 3]:
            if len(results) >= max_results:
                break

            link_tag = li.select_one("a.link")
            if not link_tag:
                link_tag = li.select_one("a")
            if not link_tag:
                continue

            title_span = li.select_one("span.title")
            subtitle_span = li.select_one("span.subtitle")
            title = _clean(title_span.get_text()) if title_span else ""
            author = _clean(subtitle_span.get_text()) if subtitle_span else ""

            # Detect and filter by language
            lang = _detect_gutenberg_lang(title)
            if lang.lower() not in _GUTENBERG_ALLOWED:
                continue

            href = link_tag.get("href", "")
            if href and not href.startswith("http"):
                href = "https://www.gutenberg.org" + href

            # Extract book id for download links
            m = re.search(r"/ebooks/(\d+)", href)
            if not m:
                continue
            book_id = m.group(1)

            cover = f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.cover.medium.jpg"

            downloads = [
                DownloadLink(
                    url=f"https://www.gutenberg.org/ebooks/{book_id}.epub3.images",
                    format="epub",
                    mirror="Gutenberg",
                ),
                DownloadLink(
                    url=f"https://www.gutenberg.org/ebooks/{book_id}.epub.noimages",
                    format="epub",
                    mirror="Gutenberg (no images)",
                ),
            ]

            results.append(
                BookResult(
                    title=title or "Unknown",
                    author=author,
                    cover_url=cover,
                    source="Project Gutenberg",
                    language=lang,
                    downloads=downloads,
                )
            )
    except Exception:
        log_exception(f"Gutenberg search failed for query={query!r}")
    return results


_IA_MAX_IDS_PER_BATCH = 30


def _ia_batch_lang_check(ia_ids: list[str], lang_code: str) -> set[str]:
    """Batch-check which *ia_ids* are freely downloadable texts in *lang_code*."""
    if not ia_ids:
        return set()
    try:
        id_clause = " OR ".join(
            f"identifier:{x}" for x in ia_ids[:_IA_MAX_IDS_PER_BATCH]
        )
        q = (f"({id_clause}) AND language:({lang_code}) AND mediatype:(texts)"
             f" AND NOT collection:(inlibrary OR printdisabled)")
        with _IA_SEMAPHORE:
            resp = _get_session().get(
                "https://archive.org/advancedsearch.php",
                params={
                    "q": q,
                    "fl[]": "identifier",
                    "rows": _IA_MAX_IDS_PER_BATCH,
                    "output": "json",
                },
                timeout=TIMEOUT,
            )
        if resp.status_code != 200:
            return set()
        docs = resp.json().get("response", {}).get("docs", [])
        return {d["identifier"] for d in docs}
    except Exception:
        log_exception("Internet Archive language batch check failed")
        return set()


def _get_ia_file_links(ia_id: str) -> list[DownloadLink]:
    """Fetch epub/pdf links for a pre-verified IA item via /metadata/{id}."""
    links: list[DownloadLink] = []
    try:
        with _IA_SEMAPHORE:
            resp = _get_session().get(
                f"https://archive.org/metadata/{ia_id}", timeout=TIMEOUT,
            )
        if resp.status_code != 200:
            return links

        data = resp.json()
        # Skip access-restricted (lending library) items
        meta = data.get("metadata", {})
        if str(meta.get("access-restricted-item", "")).lower() == "true":
            return links

        seen: set[str] = set()
        for f in data.get("files", []):
            name: str = f.get("name", "")
            fmt_raw = f.get("format", "").lower()
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

            fmt = ""
            if ext == "epub" or "epub" in fmt_raw:
                fmt = "epub"
            elif ext == "pdf" or "pdf" in fmt_raw:
                fmt = "pdf"

            if not fmt or fmt in seen:
                continue
            seen.add(fmt)

            dl_url = (
                f"https://archive.org/download/{ia_id}/"
                f"{urllib.parse.quote(name)}"
            )
            links.append(
                DownloadLink(url=dl_url, format=fmt, mirror="Internet Archive")
            )
            if len(links) >= 4:
                break
    except Exception:
        log_exception(f"Internet Archive metadata fetch failed for ia_id={ia_id!r}")
    return links



def _search_ol_single_language(
    query: str, lang_code: str, lang_label: str, max_results: int = 10,
) -> list[BookResult]:
    """Search Open Library for books in one language, verify via IA batch check."""
    results: list[BookResult] = []
    try:
        resp = _get_session().get("https://openlibrary.org/search.json", params={
            "q": query, "language": lang_code, "limit": max_results * 3,
            "sort": "rating",
            "fields": "key,title,author_name,first_publish_year,cover_i,ia,ratings_average,ratings_count,subject,first_sentence",
        }, timeout=TIMEOUT)
        resp.raise_for_status()
        docs = resp.json().get("docs", [])

        # De-duplicate by title and collect IA IDs
        seen_titles: set[str] = set()
        filtered_docs: list[dict] = []
        all_ia_ids: list[str] = []
        for doc in docs:
            title = doc.get("title", "Unknown")
            title_key = title.strip().lower()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            ia_list = doc.get("ia", [])
            if not ia_list:
                continue
            kept = ia_list[:3]
            doc["_ia_kept"] = kept
            all_ia_ids.extend(kept)
            filtered_docs.append(doc)

            if len(filtered_docs) >= max_results * 2:
                break

        if not all_ia_ids:
            return results

        matched_ids = _ia_batch_lang_check(all_ia_ids, lang_code)
        if not matched_ids:
            return results

        doc_ia: list[tuple[dict, str]] = []
        for doc in filtered_docs:
            for ia_id in doc["_ia_kept"]:
                if ia_id in matched_ids:
                    doc_ia.append((doc, ia_id))
                    break
            if len(doc_ia) >= max_results:
                break

        if not doc_ia:
            return results


        unique_ids = list({ia_id for _, ia_id in doc_ia})
        ia_files: dict[str, list[DownloadLink]] = {}

        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(_get_ia_file_links, ia_id): ia_id
                    for ia_id in unique_ids}
            for fut in as_completed(futs):
                ia_id = futs[fut]
                ia_files[ia_id] = fut.result()


        for doc, ia_id in doc_ia:
            downloads = ia_files.get(ia_id, [])
            if not downloads:
                continue

            title = doc.get("title", "Unknown")
            cover_id = doc.get("cover_i")
            results.append(
                BookResult(
                    title=title,
                    author=", ".join(doc.get("author_name", [])),
                    cover_url=(
                        f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                        if cover_id else ""
                    ),
                    year=str(doc.get("first_publish_year", "")),
                    source="Open Library",
                    language=lang_label,
                    rating=round(doc.get("ratings_average", 0) or 0, 1),
                    ratings_count=doc.get("ratings_count", 0) or 0,
                    description=_extract_first_sentence(doc.get("first_sentence")),
                    subjects=_extract_subjects(doc.get("subject", [])),
                    downloads=downloads,
                )
            )
            if len(results) >= max_results:
                break
    except Exception:
        log_exception(f"Open Library search failed for query={query!r} lang={lang_code!r}")
    return results


# ── External book source ─────────────────────────────────────────

_FALLBACK_MIRRORS = [
    "https://libgen.vg",
    "https://libgen.la",
    "https://libgen.bz",
    "https://libgen.gl",
    "https://libgen.li",
    "https://libgen.lc",
    "https://libgen.gs",
]

_cached_mirror: str | None = None
_mirror_lock = threading.Lock()


def _find_mirror() -> str | None:
    """Return a working mirror URL (cached after first success).

    If the BOOK_SOURCE environment variable is set, use that URL directly
    (skip mirror probing).  Otherwise fall back to probing known mirrors.
    """
    global _cached_mirror
    if _cached_mirror is not None:
        return _cached_mirror
    with _mirror_lock:
        if _cached_mirror is not None:          # double-check
            return _cached_mirror
        # Prefer explicit env var
        env_url = os.environ.get("BOOK_SOURCE", "").strip().rstrip("/")
        if env_url:
            _cached_mirror = env_url
            return env_url
        # Auto-discover from fallback list
        for base in _FALLBACK_MIRRORS:
            try:
                r = _get_session().head(base + "/index.php", timeout=6,
                                        allow_redirects=True)
                if r.status_code == 200:
                    _cached_mirror = base
                    return base
            except Exception:
                continue
    return None


def _search_external(query: str, max_results: int = 12) -> list[BookResult]:
    """Search external book source for epub/pdf books."""
    mirror = _find_mirror()
    if not mirror:
        return []

    results: list[BookResult] = []
    try:
        params = {
            "req": query,
            "res": 25,
            "gmode": "on",
            "topics[]": ["l", "f"],
        }
        resp = _get_session().get(
            f"{mirror}/index.php", params=params, timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", class_=re.compile(r"table"))
        if not table:
            return results

        rows = table.find_all("tr")
        seen_titles: set[str] = set()

        for row in rows[1:]:  # skip header
            tds = row.find_all("td")
            if len(tds) < 9:
                continue

            # Extension (TD7) – only keep epub/pdf
            ext = tds[7].get_text(strip=True).lower()
            if ext not in ("epub", "pdf"):
                continue

            # Title (TD0) – from edition.php link text
            title = ""
            for a in tds[0].find_all("a", href=re.compile(r"edition\.php")):
                t = a.get_text(strip=True)
                # Skip ISBNs (digits/semicolons only)
                if t and not re.match(r"^[\d;\s-]+$", t):
                    title = t
                    break
            if not title:
                continue

            # De-duplicate by title
            title_key = title.strip().lower()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            author = _clean(tds[1].get_text())
            year = tds[3].get_text(strip=True)
            lang = tds[4].get_text(strip=True)
            size = tds[6].get_text(strip=True)

            # Extract MD5 from mirror links in TD8
            md5 = ""
            for a in tds[8].find_all("a", href=True):
                m = re.search(r"[a-fA-F0-9]{32}", a["href"])
                if m:
                    md5 = m.group(0)
                    break
            if not md5:
                continue

            # Build download link via ads.php (resolved at download time)
            dl_url = f"{mirror}/ads.php?md5={md5}"
            downloads = [
                DownloadLink(
                    url=dl_url,
                    format=ext,
                    mirror=f"External ({size})",
                ),
            ]

            results.append(BookResult(
                title=title,
                author=author,
                year=year,
                source="External",
                language=lang,
                description=f"External source file size: {size}",
                downloads=downloads,
            ))
            if len(results) >= max_results:
                break
    except Exception:
        log_exception(f"External source search failed for query={query!r}")
    return results


def resolve_external_download(ads_url: str) -> str | None:
    """Given an ads.php URL, resolve to the actual direct-download URL.

    Fetches the ads page, finds the get.php?md5=...&key=... link, and
    returns the full URL ready for download.
    """
    try:
        resp = _get_session().get(ads_url, timeout=TIMEOUT)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.find_all("a"):
            if a.get_text(strip=True).upper() == "GET":
                href = a.get("href", "")
                if "get.php" in href and "key=" in href:
                    if href.startswith("http"):
                        return href
                    # Derive base from ads_url
                    from urllib.parse import urlparse
                    p = urlparse(ads_url)
                    return f"{p.scheme}://{p.netloc}/{href.lstrip('/')}"
    except Exception:
        log_exception("External download resolution failed")
    return None


def _extract_first_sentence(value: object) -> str:
    if isinstance(value, dict):
        text = value.get("value", "")
        return _clean(str(text))
    if isinstance(value, list) and value:
        return _clean(str(value[0]))
    if isinstance(value, str):
        return _clean(value)
    return ""


def _extract_subjects(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: list[str] = []
    for item in value:
        text = _clean(str(item))
        if text and text not in seen:
            seen.append(text)
        if len(seen) >= 5:
            break
    return seen


def _normalise_title(title: str) -> str:
    """Lower-case, strip subtitles / parenthetical notes, collapse whitespace."""
    t = title.strip().lower()
    t = re.sub(r"\s*[\(\[].*?[\)\]]", "", t)   # remove (…) and [...]
    t = re.sub(r"\s*[:–—\-].{15,}$", "", t)    # remove long subtitles
    t = re.sub(r"[^a-z0-9 ]", "", t)           # only alphanumeric + space
    return re.sub(r"\s+", " ", t).strip()


def _title_similarity(a: str, b: str) -> float:
    """Similarity between two normalised titles (0..1).

    Combines word overlap with substring containment bonus so that
    'the little prince' ranks highest for query 'the little prince',
    above 'the cruel prince' which merely shares common words.
    """
    if not a or not b:
        return 0.0
    # Exact match
    if a == b:
        return 1.0
    # Substring containment → strong signal (only if shorter part is meaningful)
    if len(a) >= 10 and len(b) >= 10:
        if a in b or b in a:
            shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
            return 0.85 + 0.15 * (len(shorter) / len(longer))
    # Word-overlap ratio as fallback
    wa = set(a.split())
    wb = set(b.split())
    overlap = wa & wb
    # Penalise common stop-words contributing to overlap
    stops = {"the", "a", "an", "of", "and", "in", "on", "to", "for", "at", "by"}
    meaningful = overlap - stops
    if not meaningful:
        return len(overlap) / (max(len(wa), len(wb)) * 3)  # heavily discount
    return len(overlap) / max(len(wa), len(wb))


def _fetch_ol_ratings(query: str, results: list[BookResult]) -> None:
    """Enrich results that lack ratings via Open Library search.

    Uses fuzzy title matching so books from any source (Gutenberg, External,
    etc.) can be matched to OL rating data even when titles differ slightly.
    """
    need_rating = [r for r in results if r.rating == 0.0 and r.title]
    if not need_rating:
        return
    try:
        from collections import defaultdict

        # Build normalised-title → list[BookResult]
        by_norm: dict[str, list[BookResult]] = defaultdict(list)
        for r in need_rating:
            by_norm[_normalise_title(r.title)].append(r)

        resp = _get_session().get("https://openlibrary.org/search.json", params={
            "q": query, "limit": 30, "sort": "rating",
            "fields": "title,ratings_average,ratings_count",
        }, timeout=TIMEOUT)
        if resp.status_code != 200:
            return

        docs = resp.json().get("docs", [])

        # First pass: exact normalised-title match
        matched_keys: set[str] = set()
        for doc in docs:
            if not doc.get("ratings_average"):
                continue
            doc_norm = _normalise_title(doc.get("title", ""))
            if doc_norm in by_norm and doc_norm not in matched_keys:
                matched_keys.add(doc_norm)
                rating = round(doc["ratings_average"], 1)
                count = doc.get("ratings_count", 0) or 0
                for r in by_norm[doc_norm]:
                    r.rating = rating
                    r.ratings_count = count

        # Second pass: fuzzy match remaining unmatched results
        unmatched = {k: v for k, v in by_norm.items() if k not in matched_keys}
        if unmatched:
            for doc in docs:
                if not doc.get("ratings_average"):
                    continue
                doc_norm = _normalise_title(doc.get("title", ""))
                for key in list(unmatched):
                    if _title_similarity(key, doc_norm) >= 0.8:
                        rating = round(doc["ratings_average"], 1)
                        count = doc.get("ratings_count", 0) or 0
                        for r in unmatched[key]:
                            if r.rating == 0.0:  # don't overwrite
                                r.rating = rating
                                r.ratings_count = count
                        del unmatched[key]
                if not unmatched:
                    break

        # Third pass: for results whose title contains the search query,
        # assign the best OL rating (handles cross-language OL entries like
        # "Le petit prince" enriching "The Little Prince …" results).
        still_unrated = [r for r in need_rating if r.rating == 0.0]
        if still_unrated and docs:
            query_norm = _normalise_title(query)
            # Use the first rated OL doc (already sorted by rating=relevance)
            best_doc = next(
                (d for d in docs if d.get("ratings_average")),
                None,
            )
            if best_doc and len(query_norm) >= 8:
                best_rating = round(best_doc["ratings_average"], 1)
                best_count = best_doc.get("ratings_count", 0) or 0
                for r in still_unrated:
                    r_norm = _normalise_title(r.title)
                    if len(r_norm) >= 10 and query_norm in r_norm:
                        r.rating = best_rating
                        r.ratings_count = best_count
    except Exception:
        log_exception(f"Open Library rating enrichment failed for query={query!r}")


def search_books(query: str, allowed_sources: list[str] | None = None) -> list[BookResult]:
    """Search all sources in parallel and return merged results."""
    if not query or not query.strip():
        return []
    enabled = set(allowed_sources or ["Project Gutenberg", "Open Library", "External"])

    with ThreadPoolExecutor(max_workers=4) as pool:
        gut_fut = pool.submit(_search_gutenberg, query) if "Project Gutenberg" in enabled else None
        ol_eng_fut = pool.submit(
            _search_ol_single_language, query, "eng", "English", 8,
        ) if "Open Library" in enabled else None
        ol_tur_fut = pool.submit(
            _search_ol_single_language, query, "tur", "Turkish", 3,
        ) if "Open Library" in enabled else None
        ext_fut = pool.submit(_search_external, query, 10) if "External" in enabled else None

        results: list[BookResult] = []
        if gut_fut:
            results.extend(gut_fut.result())
        if ol_eng_fut:
            results.extend(ol_eng_fut.result())
        if ol_tur_fut:
            results.extend(ol_tur_fut.result())
        if ext_fut:
            results.extend(ext_fut.result())

    # Enrich all unrated results with OL ratings (best-effort)
    _fetch_ol_ratings(query, results)

    # Sort by combined relevance × popularity score
    import math
    query_norm = _normalise_title(query)

    def _sort_key(r: BookResult) -> float:
        relevance = _title_similarity(_normalise_title(r.title), query_norm)
        # Boost: at least 0.1 so rated but less-relevant books still rank
        relevance = max(relevance, 0.1)
        popularity = math.log2(r.ratings_count + 1)
        return relevance * popularity

    results.sort(key=_sort_key, reverse=True)

    return results
