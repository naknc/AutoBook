# AutoBook Release Notes

## Highlights

- Professional desktop workspace redesign
- Centralized logging and error observability
- Advanced search, filtering and offline cache
- Library metadata management, collections and bulk tools
- Download queue with retry, cancel and reorder
- Device profiles and transfer history
- OCR, conversion and repair actions
- AI-assisted enrichment hooks
- Plugin import/toggle support
- Local web companion preview

## System Requirements

- `tesseract` for OCR
- `pandoc` and `ebook-convert` for conversion
- Optional `OPENAI_API_KEY` for AI features

## Companion Outputs

- `library/companion/library_feed.json`
- `library/companion/index.html`

## Recommended Launch Flow

1. Open the app with `uv run main.py`
2. Search and download one title
3. Verify queue and history behavior
4. Open Library and test one file action
5. Open Settings and verify diagnostics
