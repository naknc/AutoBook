#!/usr/bin/env python3
"""AutoBook desktop workspace. Run with: uv run main.py"""

from __future__ import annotations

import io
import platform
import subprocess
import threading
import tkinter as tk
from collections import Counter
from typing import Any, Callable

import customtkinter as ctk
import requests
from PIL import Image

from app.devices import copy_to_device, detect_devices
from app.library import (
    LIBRARY_DIR,
    add_to_library,
    get_all_books,
    get_book_path,
    remove_from_library,
)
from app.search import BookResult, resolve_external_download, search_books

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

_NAV_BG = "#0F172A"
_APP_BG = "#0B1220"
_SURFACE = "#111827"
_SURFACE_ALT = "#1F2937"
_CARD_BG = "#162033"
_CARD_BORDER = "#273449"
_TEXT = "#E5EEF9"
_TEXT_MUTED = "#93A4BC"
_TEXT_SOFT = "#6F839E"
_ACCENT = "#2F6FED"
_ACCENT_HOVER = "#275DCA"
_ACCENT_SOFT = "#17305F"
_SUCCESS = "#17B26A"
_WARNING = "#F59E0B"
_DANGER = "#D64545"
_DANGER_HOVER = "#B83838"

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}


def _load_cover(url: str, size: tuple[int, int] = (100, 150)) -> ctk.CTkImage | None:
    if not url:
        return None
    try:
        response = requests.get(url, timeout=8, headers=_UA)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content))
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)
    except Exception:
        return None


def _safe_filename(title: str, fmt: str) -> str:
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:80].strip()
    return f"{safe}.{fmt}" if safe else f"book.{fmt}"


def _rating_stars(rating: float) -> str:
    full = int(rating)
    half = 1 if rating - full >= 0.3 else 0
    empty = 5 - full - half
    return "★" * full + ("½" if half else "") + "☆" * empty


class ScrollableFrame(tk.Frame):
    """Text-widget-based scrollable container with native trackpad scrolling."""

    def __init__(self, master, fg_color=_APP_BG, **kw):
        super().__init__(master, bg=fg_color, **kw)

        self._text = tk.Text(
            self,
            bg=fg_color,
            cursor="arrow",
            wrap="none",
            borderwidth=0,
            highlightthickness=0,
            padx=2,
            pady=2,
            state="disabled",
        )
        self._text.pack(fill="both", expand=True)

        self.inner = tk.Frame(self._text, bg=fg_color)
        self._text.configure(state="normal")
        self._text.window_create("1.0", window=self.inner, stretch=True)
        self._text.configure(state="disabled")
        self._text.bind("<Configure>", self._on_resize)

    def winfo_children(self):
        return self.inner.winfo_children()

    def _on_resize(self, _event=None):
        width = self._text.winfo_width() - 6
        if width > 10:
            self.inner.configure(width=width)


class AutoBookApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AutoBook Workspace")
        self.geometry("1240x820")
        self.minsize(980, 640)
        self.configure(fg_color=_APP_BG)

        self._image_refs: list[ctk.CTkImage] = []
        self.inline_status: ctk.CTkLabel | None = None
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.active_section = "search"

        self._build_shell()
        self._show_search()

    def _build_shell(self) -> None:
        sidebar = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=_NAV_BG)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=22, pady=(24, 18))
        ctk.CTkLabel(
            brand,
            text="AutoBook",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=_TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand,
            text="Digital publishing workspace",
            font=ctk.CTkFont(size=13),
            text_color=_TEXT_MUTED,
        ).pack(anchor="w", pady=(4, 0))

        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.pack(fill="x", padx=16, pady=(8, 0))
        self._add_nav_button(nav, "search", "Catalog Search", self._show_search)
        self._add_nav_button(nav, "library", "Library", self._show_library)
        self._add_nav_button(nav, "devices", "Devices", self._show_devices)

        footer = ctk.CTkFrame(sidebar, fg_color=_SURFACE, corner_radius=18)
        footer.pack(side="bottom", fill="x", padx=16, pady=16)
        ctk.CTkLabel(
            footer,
            text="Operations",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_TEXT_MUTED,
        ).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            footer,
            text="Search, download, organize and transfer titles from one workspace.",
            font=ctk.CTkFont(size=12),
            text_color=_TEXT_SOFT,
            justify="left",
            wraplength=190,
        ).pack(anchor="w", padx=14, pady=(0, 14))

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=_APP_BG)
        self.content.pack(side="right", fill="both", expand=True)

    def _add_nav_button(
        self,
        parent: ctk.CTkFrame,
        key: str,
        label: str,
        command: Callable[[], None],
    ) -> None:
        button = ctk.CTkButton(
            parent,
            text=label,
            command=command,
            height=46,
            corner_radius=14,
            anchor="w",
            fg_color="transparent",
            hover_color=_SURFACE_ALT,
            text_color=_TEXT_MUTED,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        button.pack(fill="x", pady=4)
        self.nav_buttons[key] = button

    def _set_active_nav(self, key: str) -> None:
        self.active_section = key
        for btn_key, button in self.nav_buttons.items():
            if btn_key == key:
                button.configure(fg_color=_ACCENT_SOFT, hover_color=_ACCENT_SOFT, text_color=_TEXT)
            else:
                button.configure(fg_color="transparent", hover_color=_SURFACE_ALT, text_color=_TEXT_MUTED)

    def _clear_content(self) -> None:
        self._image_refs.clear()
        self.inline_status = None
        for widget in self.content.winfo_children():
            widget.destroy()

    def _set_status(self, msg: str) -> None:
        if self.inline_status:
            try:
                self.inline_status.configure(text=msg)
            except Exception:
                pass

    def _create_header(
        self,
        title: str,
        subtitle: str,
        action_text: str | None = None,
        action_command: Callable[[], None] | None = None,
    ) -> ctk.CTkFrame:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(24, 12))

        text_col = ctk.CTkFrame(header, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            text_col,
            text=title,
            font=ctk.CTkFont(size=30, weight="bold"),
            text_color=_TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            text_col,
            text=subtitle,
            font=ctk.CTkFont(size=14),
            text_color=_TEXT_MUTED,
        ).pack(anchor="w", pady=(4, 0))

        if action_text and action_command:
            ctk.CTkButton(
                header,
                text=action_text,
                command=action_command,
                width=112,
                height=38,
                corner_radius=14,
                fg_color=_SURFACE,
                hover_color=_SURFACE_ALT,
                border_width=1,
                border_color=_CARD_BORDER,
                text_color=_TEXT,
            ).pack(side="right")

        return header

    def _summary_row(self, items: list[tuple[str, str]]) -> None:
        row = ctk.CTkFrame(self.content, fg_color="transparent")
        row.pack(fill="x", padx=28, pady=(0, 16))
        for label, value in items:
            card = ctk.CTkFrame(row, fg_color=_SURFACE, corner_radius=18, border_width=1, border_color=_CARD_BORDER)
            card.pack(side="left", fill="both", expand=True, padx=(0, 12))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=12, weight="bold"), text_color=_TEXT_SOFT).pack(
                anchor="w", padx=16, pady=(14, 4)
            )
            ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=24, weight="bold"), text_color=_TEXT).pack(
                anchor="w", padx=16, pady=(0, 14)
            )

    def _make_surface(self, parent: ctk.CTkBaseClass, pady: tuple[int, int] = (0, 0)) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_SURFACE, corner_radius=20, border_width=1, border_color=_CARD_BORDER)
        frame.pack(fill="x", padx=28, pady=pady)
        return frame

    def _make_badge(self, parent: ctk.CTkBaseClass, text: str, fg_color: str = _ACCENT_SOFT) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            fg_color=fg_color,
            corner_radius=10,
            text_color=_TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
            padx=10,
            pady=4,
        ).pack(side="left", padx=(0, 8))

    def _show_empty_state(self, title: str, body: str, action_text: str | None = None, action_cmd: Callable[[], None] | None = None) -> None:
        card = ctk.CTkFrame(self.content, fg_color=_SURFACE, corner_radius=22, border_width=1, border_color=_CARD_BORDER)
        card.pack(fill="x", padx=28, pady=(10, 20))
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=22, weight="bold"), text_color=_TEXT).pack(
            anchor="w", padx=24, pady=(22, 8)
        )
        ctk.CTkLabel(
            card,
            text=body,
            font=ctk.CTkFont(size=14),
            text_color=_TEXT_MUTED,
            justify="left",
            wraplength=760,
        ).pack(anchor="w", padx=24, pady=(0, 18))
        if action_text and action_cmd:
            ctk.CTkButton(
                card,
                text=action_text,
                command=action_cmd,
                width=180,
                height=38,
                corner_radius=14,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOVER,
                text_color=_TEXT,
            ).pack(anchor="w", padx=24, pady=(0, 22))

    def _load_cover_async(
        self,
        url: str,
        label: ctk.CTkLabel,
        size: tuple[int, int] = (100, 150),
    ) -> None:
        def _work(u: str = url, lbl: ctk.CTkLabel = label) -> None:
            img = _load_cover(u, size)
            if img:
                self._image_refs.append(img)
                self.after(0, lambda: _apply(img, lbl))

        def _apply(img: ctk.CTkImage, lbl: ctk.CTkLabel) -> None:
            try:
                lbl.configure(image=img, text="")
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()

    def _search_summary_items(self) -> list[tuple[str, str]]:
        books = get_all_books()
        return [
            ("Indexed Sources", "4"),
            ("Local Titles", str(len(books))),
            ("Formats Ready", "EPUB / PDF"),
        ]

    def _library_summary_items(self, books: list[dict[str, Any]]) -> list[tuple[str, str]]:
        formats = {b.get("format", "").upper() for b in books if b.get("format")}
        sources = {b.get("source", "") for b in books if b.get("source")}
        return [
            ("Titles", str(len(books))),
            ("Formats", str(len(formats) or 0)),
            ("Sources", str(len(sources) or 0)),
        ]

    def _device_summary_items(self, devices: list[Any]) -> list[tuple[str, str]]:
        counts = Counter(dev.kind for dev in devices)
        return [
            ("Detected Devices", str(len(devices))),
            ("E-Readers", str(counts.get("ereader", 0) + counts.get("mtp", 0))),
            ("Tablets / Phones", str(counts.get("ipad", 0))),
        ]

    # Search page

    def _show_search(self) -> None:
        self._set_active_nav("search")
        self._clear_content()

        self._create_header(
            "Catalog Search",
            "Search public-domain and external sources, then download directly into your managed library.",
        )
        self._summary_row(self._search_summary_items())

        panel = self._make_surface(self.content, (0, 16))
        ctk.CTkLabel(
            panel,
            text="Find a title, author or keyword",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=_TEXT,
        ).pack(anchor="w", padx=22, pady=(18, 4))
        ctk.CTkLabel(
            panel,
            text="Results are ranked across Gutenberg, Open Library, Internet Archive and your configured external source.",
            font=ctk.CTkFont(size=13),
            text_color=_TEXT_MUTED,
        ).pack(anchor="w", padx=22, pady=(0, 14))

        search_row = ctk.CTkFrame(panel, fg_color="transparent")
        search_row.pack(fill="x", padx=22, pady=(0, 18))

        self.search_entry = ctk.CTkEntry(
            search_row,
            placeholder_text="Examples: Crime and Punishment, Stefan Zweig, science fiction",
            height=46,
            corner_radius=14,
            border_color=_CARD_BORDER,
            fg_color=_CARD_BG,
            text_color=_TEXT,
            placeholder_text_color=_TEXT_SOFT,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.bind("<Return>", lambda _e: self._do_search())

        ctk.CTkButton(
            search_row,
            text="Search",
            width=128,
            height=46,
            corner_radius=14,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            text_color=_TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._do_search,
        ).pack(side="right")

        self.inline_status = ctk.CTkLabel(
            self.content,
            text="Ready for search.",
            font=ctk.CTkFont(size=12),
            text_color=_TEXT_SOFT,
            anchor="w",
        )
        self.inline_status.pack(fill="x", padx=30, pady=(0, 6))

        self.results_frame = ScrollableFrame(self.content, fg_color=_APP_BG)
        self.results_frame.pack(fill="both", expand=True, padx=28, pady=(0, 18))
        self._show_search_placeholder()
        self.search_entry.focus()

    def _show_search_placeholder(self) -> None:
        placeholder = ctk.CTkFrame(self.results_frame.inner, fg_color=_SURFACE, corner_radius=22, border_width=1, border_color=_CARD_BORDER)
        placeholder.pack(fill="x", padx=2, pady=2)
        ctk.CTkLabel(
            placeholder,
            text="Discovery workspace",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=_TEXT,
        ).pack(anchor="w", padx=24, pady=(22, 8))
        ctk.CTkLabel(
            placeholder,
            text="Start a search to review availability, compare sources, inspect ratings and download files into the local catalog.",
            font=ctk.CTkFont(size=14),
            text_color=_TEXT_MUTED,
            justify="left",
            wraplength=820,
        ).pack(anchor="w", padx=24, pady=(0, 20))

    def _do_search(self) -> None:
        query = self.search_entry.get().strip()
        if not query:
            self._set_status("Please enter a search query.")
            return

        for widget in self.results_frame.winfo_children():
            widget.destroy()

        self._set_status(f'Searching sources for "{query}"...')
        self.update_idletasks()

        def _worker() -> None:
            results = search_books(query)
            self.after(0, lambda: self._display_results(results, query))

        threading.Thread(target=_worker, daemon=True).start()

    def _display_results(self, results: list[BookResult], query: str) -> None:
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        self._set_status(f'{len(results)} results found for "{query}".')

        if not results:
            empty = ctk.CTkFrame(self.results_frame.inner, fg_color=_SURFACE, corner_radius=22, border_width=1, border_color=_CARD_BORDER)
            empty.pack(fill="x", padx=2, pady=2)
            ctk.CTkLabel(empty, text="No results found", font=ctk.CTkFont(size=22, weight="bold"), text_color=_TEXT).pack(
                anchor="w", padx=24, pady=(22, 8)
            )
            ctk.CTkLabel(
                empty,
                text="Try another author, a shorter title, or a broader keyword. Public-domain catalogs are often sensitive to exact phrasing.",
                font=ctk.CTkFont(size=14),
                text_color=_TEXT_MUTED,
                justify="left",
                wraplength=820,
            ).pack(anchor="w", padx=24, pady=(0, 22))
            return

        for book in results:
            self._make_search_card(book)

    def _make_search_card(self, book: BookResult) -> None:
        card = ctk.CTkFrame(
            self.results_frame.inner,
            corner_radius=20,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_CARD_BORDER,
        )
        card.pack(fill="x", pady=6, padx=2)

        cover = ctk.CTkLabel(card, text="BOOK", width=104, height=148, fg_color=_CARD_BG, corner_radius=14, text_color=_TEXT_SOFT)
        cover.pack(side="left", padx=(16, 10), pady=16)
        if book.cover_url:
            self._load_cover_async(book.cover_url, cover)

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=8, pady=16)
        ctk.CTkLabel(
            info,
            text=book.title,
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=520,
            text_color=_TEXT,
        ).pack(anchor="w")

        if book.author:
            ctk.CTkLabel(
                info,
                text=book.author,
                font=ctk.CTkFont(size=13),
                text_color=_TEXT_MUTED,
                anchor="w",
            ).pack(anchor="w", pady=(4, 10))

        meta = ctk.CTkFrame(info, fg_color="transparent")
        meta.pack(anchor="w", pady=(0, 10))
        if book.source:
            self._make_badge(meta, book.source, _ACCENT_SOFT)
        if book.language:
            self._make_badge(meta, book.language, _CARD_BG)
        if book.year:
            self._make_badge(meta, book.year, _SURFACE_ALT)

        if book.rating > 0:
            ctk.CTkLabel(
                info,
                text=f"{_rating_stars(book.rating)}  {book.rating:.1f}  ({book.ratings_count} reviews)",
                font=ctk.CTkFont(size=12),
                text_color=_WARNING,
                anchor="w",
            ).pack(anchor="w")
        else:
            ctk.CTkLabel(
                info,
                text="No rating metadata available",
                font=ctk.CTkFont(size=12),
                text_color=_TEXT_SOFT,
                anchor="w",
            ).pack(anchor="w")

        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=16, pady=16)
        for dl in book.downloads:
            ctk.CTkButton(
                btn_frame,
                text=f"Download {dl.format.upper()}",
                width=170,
                height=36,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOVER,
                corner_radius=12,
                text_color=_TEXT,
                command=lambda d=dl, b=book: self._download_book(d, b),
            ).pack(pady=4)
            ctk.CTkLabel(
                btn_frame,
                text=dl.mirror,
                font=ctk.CTkFont(size=11),
                text_color=_TEXT_SOFT,
            ).pack(pady=(0, 4))
        if not book.downloads:
            ctk.CTkLabel(btn_frame, text="No direct file", text_color=_TEXT_SOFT).pack()

    def _download_book(self, dl: Any, book: BookResult) -> None:
        self._set_status(f'Downloading "{book.title}" as {dl.format.upper()}...')
        self.update_idletasks()

        candidates = [dl] + [d for d in book.downloads if d.url != dl.url and d.format == dl.format]

        def _try_download(link: Any) -> requests.Response | None:
            urls = [link.url]
            if "/ads.php?md5=" in link.url:
                resolved = resolve_external_download(link.url)
                if resolved:
                    urls = [resolved]
                else:
                    return None
            elif "archive.org" in link.url:
                alt = link.url.replace("//dn", "//ia").replace(".ca.archive.org", ".us.archive.org")
                if alt != link.url:
                    urls.append(alt)

            for url in urls:
                try:
                    response = requests.get(
                        url,
                        stream=True,
                        timeout=60,
                        headers=_UA,
                        allow_redirects=True,
                    )
                    if response.status_code >= 400:
                        response.close()
                        continue
                    content_type = response.headers.get("Content-Type", "")
                    if "text/html" in content_type and link.format in ("epub", "pdf"):
                        response.close()
                        continue
                    return response
                except requests.RequestException:
                    continue
            return None

        def _worker() -> None:
            for candidate in candidates:
                response = _try_download(candidate)
                if response is None:
                    continue
                dest = None
                try:
                    filename = _safe_filename(book.title, candidate.format)
                    dest = LIBRARY_DIR / filename
                    index = 1
                    while dest.exists():
                        filename = _safe_filename(f"{book.title}_{index}", candidate.format)
                        dest = LIBRARY_DIR / filename
                        index += 1
                    with open(dest, "wb") as handle:
                        for chunk in response.iter_content(8192):
                            handle.write(chunk)
                    add_to_library(filename, book.title, book.author, candidate.format, book.cover_url, book.source)
                    self.after(0, lambda: self._set_status(f'"{book.title}" added to the library.'))
                    return
                except Exception:
                    if dest and dest.exists():
                        dest.unlink(missing_ok=True)
                finally:
                    response.close()

            self.after(0, lambda: self._set_status("Download failed. All candidate sources returned errors."))

        threading.Thread(target=_worker, daemon=True).start()

    # Library page

    def _show_library(self) -> None:
        self._set_active_nav("library")
        self._clear_content()

        books = get_all_books()
        self._create_header("Library", "Manage downloaded titles, open local files and send them to connected devices.", "Refresh", self._show_library)
        self._summary_row(self._library_summary_items(books))

        self.inline_status = ctk.CTkLabel(
            self.content,
            text=f"{len(books)} local title(s) available.",
            font=ctk.CTkFont(size=12),
            text_color=_TEXT_SOFT,
            anchor="w",
        )
        self.inline_status.pack(fill="x", padx=30, pady=(0, 6))

        if not books:
            self._show_empty_state(
                "Your library is empty",
                "Search for a book and download it into the managed catalog. Each file is stored locally with metadata and device-transfer support.",
                "Go to Search",
                self._show_search,
            )
            return

        scroll = ScrollableFrame(self.content, fg_color=_APP_BG)
        scroll.pack(fill="both", expand=True, padx=28, pady=(0, 18))
        for book in books:
            self._make_library_card(scroll.inner, book)

    def _make_library_card(self, parent: ctk.Frame, book: dict[str, Any]) -> None:
        card = ctk.CTkFrame(parent, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
        card.pack(fill="x", pady=6, padx=2)

        cover = ctk.CTkLabel(card, text="FILE", width=88, height=120, fg_color=_CARD_BG, corner_radius=14, text_color=_TEXT_SOFT)
        cover.pack(side="left", padx=(16, 10), pady=16)
        if book.get("cover_url"):
            self._load_cover_async(book["cover_url"], cover, (82, 118))

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=8, pady=16)
        ctk.CTkLabel(
            info,
            text=book.get("title", "Unknown"),
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=_TEXT,
            anchor="w",
            wraplength=480,
        ).pack(anchor="w")
        if book.get("author"):
            ctk.CTkLabel(info, text=book["author"], font=ctk.CTkFont(size=13), text_color=_TEXT_MUTED, anchor="w").pack(
                anchor="w", pady=(4, 10)
            )

        meta = ctk.CTkFrame(info, fg_color="transparent")
        meta.pack(anchor="w")
        if book.get("format"):
            self._make_badge(meta, book["format"].upper(), _ACCENT_SOFT)
        if book.get("source"):
            self._make_badge(meta, book["source"], _SURFACE_ALT)

        ctk.CTkLabel(
            info,
            text=book.get("filename", ""),
            font=ctk.CTkFont(size=12),
            text_color=_TEXT_SOFT,
            anchor="w",
        ).pack(anchor="w", pady=(12, 0))

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(side="right", padx=16, pady=16)
        ctk.CTkButton(
            actions,
            text="Open File",
            width=132,
            height=34,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            corner_radius=12,
            text_color=_TEXT,
            command=lambda b=book: self._open_book_file(b),
        ).pack(pady=4)
        ctk.CTkButton(
            actions,
            text="Send to Device",
            width=132,
            height=34,
            fg_color=_SURFACE_ALT,
            hover_color=_CARD_BG,
            corner_radius=12,
            border_width=1,
            border_color=_CARD_BORDER,
            text_color=_TEXT,
            command=lambda b=book: self._send_to_device(b),
        ).pack(pady=4)
        ctk.CTkButton(
            actions,
            text="Remove",
            width=132,
            height=34,
            fg_color=_DANGER,
            hover_color=_DANGER_HOVER,
            corner_radius=12,
            text_color=_TEXT,
            command=lambda b=book: self._delete_book(b),
        ).pack(pady=4)

    def _open_book_file(self, book: dict[str, Any]) -> None:
        path = get_book_path(book["id"])
        if not path:
            self._set_status("File not found in library.")
            return
        cmd = {"Darwin": ["open", "-R"], "Linux": ["xdg-open"]}.get(platform.system(), ["explorer"])
        subprocess.Popen([*cmd, str(path if cmd[0] == "open" else path.parent)])

    def _delete_book(self, book: dict[str, Any]) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Remove Title")
        dialog.geometry("420x180")
        dialog.configure(fg_color=_SURFACE)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="Remove this title from the library?",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=_TEXT,
        ).pack(anchor="w", padx=22, pady=(22, 8))
        ctk.CTkLabel(
            dialog,
            text=book.get("title", "Unknown"),
            font=ctk.CTkFont(size=14),
            text_color=_TEXT_MUTED,
            wraplength=360,
            justify="left",
        ).pack(anchor="w", padx=22, pady=(0, 18))

        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(anchor="e", padx=22, pady=(0, 18))

        def _confirm() -> None:
            remove_from_library(book["id"])
            dialog.destroy()
            self._show_library()
            self._set_status(f'"{book.get("title", "Unknown")}" removed from the library.')

        ctk.CTkButton(
            actions,
            text="Cancel",
            fg_color=_SURFACE_ALT,
            hover_color=_CARD_BG,
            border_width=1,
            border_color=_CARD_BORDER,
            corner_radius=12,
            width=100,
            text_color=_TEXT,
            command=dialog.destroy,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Remove",
            fg_color=_DANGER,
            hover_color=_DANGER_HOVER,
            corner_radius=12,
            width=100,
            text_color=_TEXT,
            command=_confirm,
        ).pack(side="left")

    def _send_to_device(self, book: dict[str, Any]) -> None:
        devices = detect_devices()
        if not devices:
            self._set_status("No device detected. Open the Devices section to troubleshoot the connection.")
            return
        if len(devices) == 1:
            self._do_transfer(book, devices[0])
        else:
            self._show_device_picker(book, devices)

    def _show_device_picker(self, book: dict[str, Any], devices: list[Any]) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Device")
        dialog.geometry("420x340")
        dialog.configure(fg_color=_SURFACE)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Select target device", font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT).pack(
            anchor="w", padx=22, pady=(20, 8)
        )
        ctk.CTkLabel(
            dialog,
            text=f'Choose where "{book.get("title", "Unknown")}" should be transferred.',
            font=ctk.CTkFont(size=13),
            text_color=_TEXT_MUTED,
            justify="left",
            wraplength=360,
        ).pack(anchor="w", padx=22, pady=(0, 14))

        for dev in devices:
            kind = {"ipad": "Tablet", "ereader": "E-Reader", "mtp": "E-Reader (MTP)"}.get(dev.kind, "USB")
            ctk.CTkButton(
                dialog,
                text=f"{dev.name}  •  {kind}",
                height=40,
                fg_color=_CARD_BG,
                hover_color=_SURFACE_ALT,
                corner_radius=12,
                border_width=1,
                border_color=_CARD_BORDER,
                text_color=_TEXT,
                command=lambda d=dev: (dialog.destroy(), self._do_transfer(book, d)),
            ).pack(fill="x", padx=22, pady=4)

    def _do_transfer(self, book: dict[str, Any], device: Any) -> None:
        path = get_book_path(book["id"])
        if not path:
            self._set_status("File not found in library.")
            return
        try:
            result = copy_to_device(str(path), device)
            self._set_status(f'Transfer completed to {device.name}. {result}')
        except Exception as exc:
            self._set_status(f"Transfer failed: {exc}")

    # Devices page

    def _show_devices(self) -> None:
        self._set_active_nav("devices")
        self._clear_content()

        self._create_header("Devices", "Review connected reading devices, install MTP support and run connection diagnostics.", "Scan", self._show_devices)
        devices = detect_devices()
        self._summary_row(self._device_summary_items(devices))

        self.inline_status = ctk.CTkLabel(
            self.content,
            text="Connection scan complete.",
            font=ctk.CTkFont(size=12),
            text_color=_TEXT_SOFT,
            anchor="w",
        )
        self.inline_status.pack(fill="x", padx=30, pady=(0, 6))
        self.update_idletasks()

        if not devices:
            from app.devices import _has_mtp_tools

            mtp_ok = _has_mtp_tools()
            is_sequoia = platform.system() == "Darwin" and int(platform.mac_ver()[0].split(".")[0]) >= 13

            message = (
                "No e-reader or tablet was detected. Verify that the device is unlocked, connected with a data cable, "
                "and trusted by the computer if applicable."
            )
            if is_sequoia:
                message += " On recent macOS versions, USB accessory approval in Privacy & Security may also block discovery."
            if not mtp_ok:
                message += " Newer Kindle firmware often requires MTP support to be installed."

            self._show_empty_state("No devices detected", message)

            action_row = ctk.CTkFrame(self.content, fg_color="transparent")
            action_row.pack(fill="x", padx=28, pady=(0, 20))

            if not mtp_ok:
                ctk.CTkButton(
                    action_row,
                    text="Install MTP Support",
                    width=180,
                    height=38,
                    fg_color=_ACCENT,
                    hover_color=_ACCENT_HOVER,
                    corner_radius=14,
                    text_color=_TEXT,
                    command=self._install_mtp,
                ).pack(side="left", padx=(0, 10))

            ctk.CTkButton(
                action_row,
                text="Run USB Diagnostics",
                width=180,
                height=38,
                fg_color=_SURFACE,
                hover_color=_SURFACE_ALT,
                border_width=1,
                border_color=_CARD_BORDER,
                corner_radius=14,
                text_color=_TEXT,
                command=self._run_usb_troubleshoot,
            ).pack(side="left")

            self._set_status("No device detected.")
            return

        self._set_status(f"{len(devices)} device(s) detected.")

        scroll = ScrollableFrame(self.content, fg_color=_APP_BG)
        scroll.pack(fill="both", expand=True, padx=28, pady=(0, 18))

        kind_map = {
            "ereader": "E-Reader",
            "ipad": "Tablet / Phone",
            "mtp": "E-Reader (MTP)",
        }
        for dev in devices:
            card = ctk.CTkFrame(scroll.inner, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
            card.pack(fill="x", pady=6, padx=2)

            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(side="left", fill="both", expand=True, padx=18, pady=16)
            ctk.CTkLabel(left, text=dev.name, font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT).pack(anchor="w")
            ctk.CTkLabel(left, text=kind_map.get(dev.kind, "USB Storage"), font=ctk.CTkFont(size=13), text_color=_TEXT_MUTED).pack(
                anchor="w", pady=(4, 10)
            )

            badges = ctk.CTkFrame(left, fg_color="transparent")
            badges.pack(anchor="w", pady=(0, 10))
            self._make_badge(badges, kind_map.get(dev.kind, "USB Storage"), _ACCENT_SOFT)
            if dev.mount_point:
                self._make_badge(badges, "Mounted", _SUCCESS)
            elif dev.kind == "mtp":
                self._make_badge(badges, "MTP Ready", _SUCCESS)
            else:
                self._make_badge(badges, "Manual Access", _SURFACE_ALT)

            path_text = dev.mount_point or "No direct mount point available"
            ctk.CTkLabel(left, text=path_text, font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w", wraplength=720).pack(
                anchor="w"
            )
            if dev.status:
                ctk.CTkLabel(left, text=dev.status, font=ctk.CTkFont(size=12), text_color=_WARNING, anchor="w", wraplength=720).pack(
                    anchor="w", pady=(8, 0)
                )

    def _install_mtp(self) -> None:
        import shutil as _shutil

        if not _shutil.which("brew"):
            self._set_status("Homebrew not found. Install Homebrew first to add MTP support.")
            return

        self._set_status("Installing MTP support via Homebrew...")
        self.update_idletasks()

        def _do_install() -> None:
            try:
                subprocess.run(["brew", "install", "libmtp"], capture_output=True, timeout=120)
                self.after(0, lambda: self._set_status("MTP support installed. Run a new device scan."))
            except Exception as exc:
                self.after(0, lambda: self._set_status(f"Install failed: {exc}"))

        threading.Thread(target=_do_install, daemon=True).start()

    # Diagnostics

    def _run_usb_troubleshoot(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("USB Diagnostics")
        dialog.geometry("620x500")
        dialog.configure(fg_color=_APP_BG)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="USB Diagnostics", font=ctk.CTkFont(size=22, weight="bold"), text_color=_TEXT).pack(
            anchor="w", padx=20, pady=(18, 6)
        )
        ctk.CTkLabel(
            dialog,
            text="The report checks the USB bus, MTP tooling and mounted volumes to help explain why a reader may not appear.",
            font=ctk.CTkFont(size=13),
            text_color=_TEXT_MUTED,
            justify="left",
            wraplength=560,
        ).pack(anchor="w", padx=20, pady=(0, 12))

        result_text = ctk.CTkTextbox(
            dialog,
            fg_color=_SURFACE,
            text_color=_TEXT,
            font=ctk.CTkFont(family="Menlo", size=12),
            corner_radius=16,
            wrap="word",
        )
        result_text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        result_text.insert("end", "Running diagnostics...\n")
        dialog.update_idletasks()

        def _diagnose() -> str:
            lines: list[str] = []
            try:
                out = subprocess.check_output(["system_profiler", "SPUSBDataType", "-detailLevel", "mini"], text=True, timeout=5)
                usb_devs = [
                    line.strip().rstrip(":")
                    for line in out.splitlines()
                    if line.strip().endswith(":") and ":" not in line.strip()[:-1] and "USB" not in line.strip() and "Host" not in line.strip()
                ]
                if usb_devs:
                    lines.append(f"[OK] USB devices found: {', '.join(usb_devs)}")
                else:
                    lines.append("[FAIL] No USB devices found on the bus.")

                has_kindle = any("kindle" in dev.lower() or "amazon" in dev.lower() for dev in usb_devs)
                lines.append("[OK] Kindle detected on USB bus." if has_kindle else "[FAIL] Kindle not visible on USB bus.")
            except Exception:
                lines.append("[WARN] Could not scan the USB bus.")

            import shutil

            if shutil.which("mtp-detect"):
                lines.append("[OK] libmtp is installed.")
                try:
                    out = subprocess.check_output(["mtp-detect"], text=True, stderr=subprocess.STDOUT, timeout=10)
                    if "1949" in out or "kindle" in out.lower() or "amazon" in out.lower():
                        lines.append("[OK] Kindle-like device found via MTP.")
                    elif "No raw devices" in out:
                        lines.append("[FAIL] mtp-detect did not find any MTP devices.")
                    else:
                        lines.append(f"[WARN] mtp-detect response: {out.strip()[:100]}")
                except Exception:
                    lines.append("[WARN] mtp-detect timed out.")
            else:
                lines.append("[FAIL] libmtp is not installed. Run: brew install libmtp")

            from pathlib import Path

            try:
                volumes = [
                    volume
                    for volume in Path("/Volumes").iterdir()
                    if volume.is_dir() and volume.name.lower() not in {"macintosh hd", "macintosh hd - data", "recovery"}
                ]
            except Exception:
                volumes = []

            if volumes:
                lines.append(f"[OK] Mounted external volumes: {', '.join(v.name for v in volumes)}")
            else:
                lines.append("[FAIL] No external volumes are mounted.")

            try:
                version = int(platform.mac_ver()[0].split(".")[0])
                if version >= 13:
                    lines.append("")
                    lines.append("macOS USB accessory approval can block new readers.")
                    lines.append("Check: System Settings > Privacy & Security > Allow accessories to connect.")
                # no else branch needed
            except Exception:
                pass

            lines.append("")
            lines.append("Recommended next steps:")
            lines.append("1. Use a verified data cable and plug directly into the computer.")
            lines.append("2. Unlock the reader and accept any trust or USB prompts.")
            lines.append("3. Reconnect the cable after changing macOS USB accessory settings.")
            lines.append("4. Install libmtp if the device uses MTP instead of USB mass storage.")
            return "\n".join(lines)

        def _run() -> None:
            report = _diagnose()
            self.after(
                0,
                lambda: (
                    result_text.delete("1.0", "end"),
                    result_text.insert("end", report),
                ),
            )

        threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    AutoBookApp().mainloop()
