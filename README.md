# 🌸 AutoBook

A desktop e-book downloader and library manager with a girly dark-mode UI, built with Python and customtkinter.

## Features

- **Multi-source search** — Finds books across Project Gutenberg, Open Library, Internet Archive, and an external book source (configurable via env var), all queried in parallel
- **Popularity-based ranking** — Results are sorted by a combined relevance × popularity score using Open Library ratings (fuzzy title matching enriches results from every source)
- **Star ratings** — Each result shows its community rating (★) and review count
- **One-click download** — Download EPUB or PDF with automatic mirror fallback
- **Local library** — All downloaded books are stored and managed locally with cover art and metadata
- **Device transfer** — Detects connected USB e-readers (Kobo, etc.), MTP devices, and iPads; send books directly to a device
- **USB troubleshooter** — Built-in diagnostic dialog for macOS USB/MTP connection issues
- **Trackpad-friendly scrolling** — Custom Text-widget-based scrollable frame for smooth trackpad scrolling on macOS (Tk 9.x)
- **Girly dark theme** — Pink, rose, lavender, and mauve palette throughout

## Requirements

- **Python** ≥ 3.10
- **uv** — Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **macOS** — Tested on macOS Sequoia (Apple Silicon). Other platforms may work but are untested.

## Setup & Run

```bash
cd AutoBook_nihos
uv run main.py
```

`uv` creates the virtual environment and installs all dependencies automatically on first run.

### Environment Variables

| Variable | Description |
|---|---|
| `BOOK_SOURCE` | Base URL for the external book source. When set, mirror auto-discovery is skipped and this URL is used directly. |

Example:

```bash
export BOOK_SOURCE="https://example.com"
uv run main.py
```

## Project Structure

```
AutoBook_nihos/
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
