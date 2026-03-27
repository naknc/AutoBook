"""Document repair, OCR and conversion helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.library import LIBRARY_DIR, get_book, get_book_path, update_book
from app.logging_utils import log_exception


def get_tooling_status() -> dict[str, bool]:
    return {
        "tesseract": shutil.which("tesseract") is not None,
        "pandoc": shutil.which("pandoc") is not None,
        "ebook-convert": shutil.which("ebook-convert") is not None,
    }


def run_ocr_for_book(book_id: str) -> dict[str, Any]:
    book = get_book(book_id)
    path = get_book_path(book_id)
    if not book or not path:
        raise FileNotFoundError("Book file could not be found.")
    if path.suffix.lower() != ".pdf":
        raise ValueError("OCR is currently available for PDF files only.")
    if not get_tooling_status()["tesseract"]:
        raise RuntimeError("Tesseract is not installed on this machine.")

    out_path = path.with_suffix(".ocr.txt")
    try:
        result = subprocess.run(
            ["tesseract", str(path), str(out_path.with_suffix("")), "-l", "eng"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "OCR process failed.")
        text = out_path.read_text(errors="ignore")[:4000]
        update_book(
            book_id,
            notes=((book.get("notes", "") + "\n\nOCR Extract:\n" + text[:1500]).strip()),
        )
        return {"output": str(out_path.relative_to(LIBRARY_DIR)), "chars": len(text)}
    except Exception:
        log_exception(f"OCR failed for book_id={book_id!r}")
        raise


def convert_book_format(book_id: str, target_format: str) -> dict[str, Any]:
    book = get_book(book_id)
    path = get_book_path(book_id)
    if not book or not path:
        raise FileNotFoundError("Book file could not be found.")

    target = target_format.lower().strip()
    if target not in {"epub", "pdf", "txt"}:
        raise ValueError("Unsupported target format.")

    tooling = get_tooling_status()
    output_path = path.with_suffix(f".{target}")

    try:
        if target == "txt":
            if path.suffix.lower() == ".txt":
                raise ValueError("Book is already in TXT format.")
            if tooling["pandoc"]:
                result = subprocess.run(
                    ["pandoc", str(path), "-o", str(output_path)],
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "Pandoc conversion failed.")
            else:
                raise RuntimeError("Pandoc is not installed on this machine.")
        else:
            if tooling["ebook-convert"]:
                result = subprocess.run(
                    ["ebook-convert", str(path), str(output_path)],
                    capture_output=True,
                    text=True,
                    timeout=240,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "ebook-convert failed.")
            else:
                raise RuntimeError("ebook-convert is not installed on this machine.")

        return {"output": str(output_path.relative_to(LIBRARY_DIR.parent)), "format": target.upper()}
    except Exception:
        log_exception(f"Format conversion failed for book_id={book_id!r} target={target!r}")
        raise


def repair_book_file(book_id: str) -> dict[str, Any]:
    path = get_book_path(book_id)
    if not path:
        raise FileNotFoundError("Book file could not be found.")
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            data = path.read_bytes()
            if not data.startswith(b"%PDF-"):
                repaired = b"%PDF-1.4\n" + data.lstrip()
                path.write_bytes(repaired)
                return {"status": "repaired", "message": "PDF header was repaired."}
            return {"status": "healthy", "message": "PDF header is already valid."}
        if suffix == ".epub":
            import zipfile

            with zipfile.ZipFile(path, "r") as archive:
                names = archive.namelist()
                if "mimetype" in names:
                    return {"status": "healthy", "message": "EPUB structure looks valid."}
                raise RuntimeError("EPUB archive is missing mimetype and requires a fresh source file.")
        return {"status": "skipped", "message": "No automatic repair available for this format."}
    except Exception:
        log_exception(f"File repair failed for book_id={book_id!r}")
        raise


def export_library_web_preview() -> Path:
    payload = {
        "generated_at": str(Path.cwd()),
        "index": "Use companion/library_feed.json as a simple browser-facing payload.",
    }
    path = LIBRARY_DIR / "companion" / "web_preview.json"
    path.write_text(json.dumps(payload, indent=2))
    return path
