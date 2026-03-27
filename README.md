# AutoBook

A desktop e-book discovery, download, and device-transfer workspace built with Python and customtkinter.

## Features

- **Multi-source search** — Finds books across Project Gutenberg, Open Library, Internet Archive, and an optional custom source (configurable via env var), all queried in parallel
- **Popularity-based ranking** — Results are sorted by a combined relevance × popularity score using Open Library ratings (fuzzy title matching enriches results from every source)
- **Star ratings** — Each result shows its community rating (★) and review count
- **One-click download** — Download EPUB or PDF with automatic mirror fallback
- **Local library** — All downloaded books are stored and managed locally with cover art and metadata
- **Device transfer** — Detects connected USB e-readers (Kobo, etc.), MTP devices, and iPads; send books directly to a device
- **USB troubleshooter** — Built-in diagnostic dialog for macOS USB/MTP connection issues
- **Trackpad-friendly scrolling** — Custom Text-widget-based scrollable frame for smooth trackpad scrolling on macOS (Tk 9.x)
- **Professional workspace UI** — A cleaner dark enterprise-style layout with dashboard summaries and structured content cards
- **Local web companion** — A small browser-based workspace with library, analytics, and history views served from a local HTTP server

## Requirements

- **Python** ≥ 3.10
- **uv** — Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **macOS** — Tested on macOS Sequoia (Apple Silicon). Other platforms may work but are untested.

## Setup & Run

```bash
cd AutoBook
uv run main.py
```

`uv` creates the virtual environment and installs all dependencies automatically on first run.

### Local Web App

Run the local browser companion:

```bash
uv run python -m app.web_companion
```

Then open the printed URL in your browser, usually `http://127.0.0.1:8765`.

### Environment Variables

| Variable | Description |
|---|---|
| `BOOK_SOURCE` | Base URL for an optional custom catalog source. When set, mirror auto-discovery is skipped and this URL is used directly. |

Example:

```bash
export BOOK_SOURCE="https://example.com"
uv run main.py
```

## Project Structure

```
AutoBook/
├── main.py              # Desktop GUI (customtkinter)
├── pyproject.toml       # Project metadata & dependencies
├── app/
│   ├── __init__.py
│   ├── search.py        # Multi-source search engine with rating enrichment
│   ├── library.py       # Library metadata & file management
│   └── devices.py       # USB / MTP / iPad detection & file transfer
└── library/             # Downloaded books stored here (auto-created)
```

## Dependencies

Managed via `uv` / `pyproject.toml`:

- **customtkinter** — Modern Tkinter widgets with dark mode
- **Pillow** — Cover image loading and resizing
- **requests** — HTTP client for search APIs and downloads
- **beautifulsoup4** + **lxml** — HTML parsing for search results
