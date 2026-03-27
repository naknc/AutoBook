#!/usr/bin/env python3
"""AutoBook desktop workspace. Run with: uv run main.py"""

from __future__ import annotations

import io
import platform
import subprocess
import threading
import tkinter as tk
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk
import requests
from PIL import Image

from app.devices import copy_to_device, detect_devices
from app.library import (
    LIBRARY_DIR,
    add_to_library,
    apply_bulk_update,
    delete_books,
    get_all_books,
    get_book,
    get_book_path,
    get_download_history,
    get_recommendations,
    get_settings,
    get_transfer_history,
    list_collections,
    list_tags,
    record_download_history,
    record_transfer_history,
    remove_from_library,
    search_books_in_library,
    set_book_collections,
    set_book_notes_and_tags,
    set_reading_status,
    toggle_favorite,
    update_book,
    update_settings,
)
from app.logging_utils import LOG_FILE, log_exception, log_info, setup_logging
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
        log_exception(f"Cover load failed for url={url!r}")
        return None


def _safe_filename(title: str, fmt: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in " -_" else "" for ch in title)[:80].strip()
    return f"{safe}.{fmt}" if safe else f"book.{fmt}"


def _rating_stars(rating: float) -> str:
    full = int(rating)
    half = 1 if rating - full >= 0.3 else 0
    empty = 5 - full - half
    return "★" * full + ("½" if half else "") + "☆" * empty


class ScrollableFrame(tk.Frame):
    """Text-based scrollable container with native trackpad scrolling."""

    _active_instance: "ScrollableFrame | None" = None
    _bindings_installed = False

    def __init__(self, master, fg_color=_APP_BG, **kwargs):
        super().__init__(master, bg=fg_color, **kwargs)
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
        self.bind("<Enter>", self._activate_scroll)
        self._text.bind("<Enter>", self._activate_scroll)
        self.inner.bind("<Enter>", self._activate_scroll)
        self.bind("<Leave>", self._deactivate_scroll)
        self._text.bind("<Leave>", self._deactivate_scroll)
        self.inner.bind("<Leave>", self._deactivate_scroll)
        self._install_global_bindings()

    def winfo_children(self):
        return self.inner.winfo_children()

    def _on_resize(self, _event=None):
        width = self._text.winfo_width() - 6
        if width > 10:
            self.inner.configure(width=width)

    @classmethod
    def _install_global_bindings(cls) -> None:
        if cls._bindings_installed:
            return
        root = tk._get_default_root()
        if root is None:
            return
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Shift-MouseWheel>"):
            root.bind_all(sequence, cls._dispatch_scroll, add="+")
        cls._bindings_installed = True

    def _activate_scroll(self, _event=None) -> None:
        ScrollableFrame._active_instance = self

    def _deactivate_scroll(self, event=None) -> None:
        if event is None:
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is None or not self._owns_widget(widget):
            if ScrollableFrame._active_instance is self:
                ScrollableFrame._active_instance = None

    def _owns_widget(self, widget: tk.Misc | None) -> bool:
        current = widget
        while current is not None:
            if current in {self, self._text, self.inner}:
                return True
            current = current.master
        return False

    @classmethod
    def _dispatch_scroll(cls, event) -> str | None:
        instance = cls._active_instance
        if instance is None or not instance.winfo_exists():
            return None
        if not instance._owns_widget(event.widget):
            return None
        return instance._on_mousewheel(event)

    def _on_mousewheel(self, event) -> str:
        try:
            if getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            else:
                raw_delta = int(getattr(event, "delta", 0))
                if raw_delta == 0:
                    return "break"
                if platform.system() == "Darwin":
                    delta = -1 if raw_delta > 0 else 1
                else:
                    delta = -max(1, min(8, abs(raw_delta) // 120 or 1)) if raw_delta > 0 else max(1, min(8, abs(raw_delta) // 120 or 1))
            self._text.yview_scroll(delta, "units")
        except Exception:
            log_exception("Trackpad scroll dispatch failed")
        return "break"


class AutoBookApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.logger = setup_logging()
        self.settings = get_settings()

        self.title("AutoBook Workspace")
        self.geometry("1280x860")
        self.minsize(1020, 680)
        self.configure(fg_color=_APP_BG)

        self._image_refs: list[ctk.CTkImage] = []
        self.inline_status: ctk.CTkLabel | None = None
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.current_search_results: list[BookResult] = []
        self.selected_book_ids: set[str] = set()
        self._build_shell()
        self._show_search()

    def _build_shell(self) -> None:
        sidebar = ctk.CTkFrame(self, width=255, corner_radius=0, fg_color=_NAV_BG)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=22, pady=(24, 18))
        ctk.CTkLabel(brand, text="AutoBook", font=ctk.CTkFont(size=28, weight="bold"), text_color=_TEXT).pack(anchor="w")
        ctk.CTkLabel(
            brand,
            text="Acquisition and library workspace",
            font=ctk.CTkFont(size=13),
            text_color=_TEXT_MUTED,
        ).pack(anchor="w", pady=(4, 0))

        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.pack(fill="x", padx=16, pady=(8, 0))
        for key, label, cmd in [
            ("search", "Catalog Search", self._show_search),
            ("library", "Library", self._show_library),
            ("history", "Download History", self._show_history),
            ("devices", "Devices", self._show_devices),
            ("settings", "Settings", self._show_settings),
        ]:
            self._add_nav_button(nav, key, label, cmd)

        footer = ctk.CTkFrame(sidebar, fg_color=_SURFACE, corner_radius=18)
        footer.pack(side="bottom", fill="x", padx=16, pady=16)
        ctk.CTkLabel(footer, text="Observability", font=ctk.CTkFont(size=12, weight="bold"), text_color=_TEXT_MUTED).pack(
            anchor="w", padx=14, pady=(12, 2)
        )
        ctk.CTkLabel(
            footer,
            text=f"Application log: {LOG_FILE.name}",
            font=ctk.CTkFont(size=12),
            text_color=_TEXT_SOFT,
            justify="left",
            wraplength=190,
        ).pack(anchor="w", padx=14, pady=(0, 14))

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=_APP_BG)
        self.content.pack(side="right", fill="both", expand=True)

    def _add_nav_button(self, parent: ctk.CTkFrame, key: str, label: str, command: Callable[[], None]) -> None:
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
        for button_key, button in self.nav_buttons.items():
            active = button_key == key
            button.configure(
                fg_color=_ACCENT_SOFT if active else "transparent",
                hover_color=_ACCENT_SOFT if active else _SURFACE_ALT,
                text_color=_TEXT if active else _TEXT_MUTED,
            )

    def _clear_content(self) -> None:
        self._image_refs.clear()
        self.inline_status = None
        for widget in self.content.winfo_children():
            widget.destroy()

    def _set_status(self, message: str) -> None:
        if self.inline_status:
            try:
                self.inline_status.configure(text=message)
            except Exception:
                log_exception("Status label update failed")

    def _refresh_settings_cache(self) -> None:
        self.settings = get_settings()

    def _create_header(self, title: str, subtitle: str, action_text: str | None = None, action_command: Callable[[], None] | None = None) -> None:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(24, 12))

        text_col = ctk.CTkFrame(header, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(text_col, text=title, font=ctk.CTkFont(size=30, weight="bold"), text_color=_TEXT).pack(anchor="w")
        ctk.CTkLabel(text_col, text=subtitle, font=ctk.CTkFont(size=14), text_color=_TEXT_MUTED).pack(anchor="w", pady=(4, 0))

        if action_text and action_command:
            ctk.CTkButton(
                header,
                text=action_text,
                command=action_command,
                width=120,
                height=38,
                corner_radius=14,
                fg_color=_SURFACE,
                hover_color=_SURFACE_ALT,
                border_width=1,
                border_color=_CARD_BORDER,
                text_color=_TEXT,
            ).pack(side="right")

    def _summary_row(self, items: list[tuple[str, str]]) -> None:
        row = ctk.CTkFrame(self.content, fg_color="transparent")
        row.pack(fill="x", padx=28, pady=(0, 16))
        for idx, (label, value) in enumerate(items):
            card = ctk.CTkFrame(row, fg_color=_SURFACE, corner_radius=18, border_width=1, border_color=_CARD_BORDER)
            card.pack(side="left", fill="both", expand=True, padx=(0, 12 if idx < len(items) - 1 else 0))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=12, weight="bold"), text_color=_TEXT_SOFT).pack(
                anchor="w", padx=16, pady=(14, 4)
            )
            ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=24, weight="bold"), text_color=_TEXT).pack(
                anchor="w", padx=16, pady=(0, 14)
            )

    def _make_surface(self, parent: Any, pady: tuple[int, int] = (0, 0)) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_SURFACE, corner_radius=20, border_width=1, border_color=_CARD_BORDER)
        frame.pack(fill="x", padx=28, pady=pady)
        return frame

    def _show_empty_state(self, title: str, body: str, action_text: str | None = None, action_cmd: Callable[[], None] | None = None) -> None:
        card = ctk.CTkFrame(self.content, fg_color=_SURFACE, corner_radius=22, border_width=1, border_color=_CARD_BORDER)
        card.pack(fill="x", padx=28, pady=(10, 20))
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=22, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=24, pady=(22, 8))
        ctk.CTkLabel(
            card,
            text=body,
            font=ctk.CTkFont(size=14),
            text_color=_TEXT_MUTED,
            justify="left",
            wraplength=820,
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

    def _make_badge(self, parent: Any, text: str, fg_color: str = _ACCENT_SOFT) -> None:
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

    def _load_cover_async(self, url: str, label: ctk.CTkLabel, size: tuple[int, int] = (100, 150)) -> None:
        def _work() -> None:
            image = _load_cover(url, size)
            if image:
                self._image_refs.append(image)
                self.after(0, lambda: label.configure(image=image, text=""))

        threading.Thread(target=_work, daemon=True, name="cover-loader").start()

    def _run_background(
        self,
        work: Callable[[], Any],
        on_success: Callable[[Any], None],
        *,
        status_message: str = "",
        user_error: str = "Operation failed.",
        success_status: str | None = None,
    ) -> None:
        if status_message:
            self._set_status(status_message)
            self.update_idletasks()

        def _runner() -> None:
            try:
                result = work()
                self.after(0, lambda: on_success(result))
                if success_status:
                    self.after(0, lambda: self._set_status(success_status))
            except Exception as exc:
                log_exception(user_error)
                self.after(0, lambda: self._set_status(f"{user_error} {exc}"))

        threading.Thread(target=_runner, daemon=True, name="autobook-worker").start()

    def _search_summary_items(self) -> list[tuple[str, str]]:
        return [("Indexed Sources", "4"), ("Local Titles", str(len(get_all_books()))), ("Log File", LOG_FILE.name)]

    def _library_summary_items(self, books: list[dict[str, Any]]) -> list[tuple[str, str]]:
        formats = {book.get("format", "").upper() for book in books if book.get("format")}
        favorites = sum(1 for book in books if book.get("favorite"))
        reading = sum(1 for book in books if book.get("reading_status") == "Reading")
        return [("Titles", str(len(books))), ("Formats", str(len(formats))), ("Favorites", str(favorites)), ("Reading", str(reading))]

    def _history_summary_items(self, history: list[dict[str, Any]]) -> list[tuple[str, str]]:
        success = sum(1 for item in history if item.get("status") == "success")
        failed = sum(1 for item in history if item.get("status") == "failed")
        return [("Events", str(len(history))), ("Success", str(success)), ("Failed", str(failed))]

    def _device_summary_items(self, devices: list[Any]) -> list[tuple[str, str]]:
        counts = Counter(device.kind for device in devices)
        return [
            ("Detected Devices", str(len(devices))),
            ("E-Readers", str(counts.get("ereader", 0) + counts.get("mtp", 0))),
            ("Tablets", str(counts.get("ipad", 0))),
        ]

    # Search page

    def _show_search(self) -> None:
        self._set_active_nav("search")
        self._clear_content()
        self._refresh_settings_cache()

        self._create_header("Catalog Search", "Search public-domain and external sources, then filter and sort the results.")
        self._summary_row(self._search_summary_items())

        panel = self._make_surface(self.content, (0, 14))
        ctk.CTkLabel(panel, text="Search catalog", font=ctk.CTkFont(size=16, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=22, pady=(18, 4))
        ctk.CTkLabel(
            panel,
            text="Filters apply instantly after a result set is loaded. Preferred source and format are preselected from settings.",
            font=ctk.CTkFont(size=13),
            text_color=_TEXT_MUTED,
        ).pack(anchor="w", padx=22, pady=(0, 14))

        search_row = ctk.CTkFrame(panel, fg_color="transparent")
        search_row.pack(fill="x", padx=22, pady=(0, 14))
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
        self.search_entry.bind("<Return>", lambda _event: self._do_search())
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

        filter_row = ctk.CTkFrame(panel, fg_color="transparent")
        filter_row.pack(fill="x", padx=22, pady=(0, 18))
        self.search_source_var = tk.StringVar(value=self.settings.get("preferred_source", "All Sources"))
        self.search_language_var = tk.StringVar(value="All Languages")
        self.search_format_var = tk.StringVar(value=self.settings.get("preferred_format", "Any"))
        self.search_rating_var = tk.StringVar(value="Any rating")
        self.search_sort_var = tk.StringVar(value="Relevance")

        self._make_filter(filter_row, "Source", self.search_source_var, ["All Sources", "Project Gutenberg", "Open Library", "External"])
        self._make_filter(filter_row, "Language", self.search_language_var, ["All Languages", "English", "Turkish", "Other"])
        self._make_filter(filter_row, "Format", self.search_format_var, ["Any", "EPUB", "PDF"])
        self._make_filter(filter_row, "Min rating", self.search_rating_var, ["Any rating", "3+", "4+"])
        self._make_filter(filter_row, "Sort", self.search_sort_var, ["Relevance", "Rating", "Newest", "Title"])

        self.inline_status = ctk.CTkLabel(self.content, text="Ready for search.", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w")
        self.inline_status.pack(fill="x", padx=30, pady=(0, 6))

        self.results_frame = ScrollableFrame(self.content, fg_color=_APP_BG)
        self.results_frame.pack(fill="both", expand=True, padx=28, pady=(0, 18))
        self._render_search_placeholder()
        self.search_entry.focus()

    def _make_filter(self, parent: ctk.CTkFrame, label: str, var: tk.StringVar, values: list[str]) -> None:
        group = ctk.CTkFrame(parent, fg_color="transparent")
        group.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(group, text=label, font=ctk.CTkFont(size=11, weight="bold"), text_color=_TEXT_SOFT).pack(anchor="w", pady=(0, 4))
        combo = ctk.CTkOptionMenu(
            group,
            values=values,
            variable=var,
            height=34,
            fg_color=_CARD_BG,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_SURFACE_ALT,
            text_color=_TEXT,
            dropdown_text_color=_TEXT,
            command=lambda _value: self._render_filtered_search_results(),
        )
        combo.pack(fill="x")

    def _render_search_placeholder(self) -> None:
        card = ctk.CTkFrame(self.results_frame.inner, fg_color=_SURFACE, corner_radius=22, border_width=1, border_color=_CARD_BORDER)
        card.pack(fill="x", padx=2, pady=2)
        ctk.CTkLabel(card, text="Discovery workspace", font=ctk.CTkFont(size=22, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=24, pady=(22, 8))
        ctk.CTkLabel(
            card,
            text="Start a search to compare sources, inspect ratings, review richer metadata and download files into the local catalog.",
            font=ctk.CTkFont(size=14),
            text_color=_TEXT_MUTED,
            justify="left",
            wraplength=840,
        ).pack(anchor="w", padx=24, pady=(0, 22))

    def _do_search(self) -> None:
        query = self.search_entry.get().strip()
        if not query:
            self._set_status("Please enter a search query.")
            return

        for widget in self.results_frame.winfo_children():
            widget.destroy()
        self._set_status(f'Searching sources for "{query}"...')
        self.update_idletasks()

        def _work() -> list[BookResult]:
            log_info(f"Running search for query={query!r}")
            return search_books(query)

        def _done(results: list[BookResult]) -> None:
            self.current_search_results = results
            self._render_filtered_search_results()

        self._run_background(_work, _done, user_error="Search failed.")

    def _render_filtered_search_results(self) -> None:
        if not hasattr(self, "results_frame"):
            return
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        results = self._apply_search_filters(self.current_search_results)
        query = self.search_entry.get().strip() if hasattr(self, "search_entry") else ""
        self._set_status(f'{len(results)} filtered result(s) for "{query}".' if query else f"{len(results)} result(s).")

        if not self.current_search_results:
            self._render_search_placeholder()
            return
        if not results:
            self._render_no_results("No results match the selected filters.")
            return
        for book in results:
            self._make_search_card(book)

    def _render_no_results(self, text: str) -> None:
        card = ctk.CTkFrame(self.results_frame.inner, fg_color=_SURFACE, corner_radius=22, border_width=1, border_color=_CARD_BORDER)
        card.pack(fill="x", padx=2, pady=2)
        ctk.CTkLabel(card, text=text, font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=24, pady=(22, 12))
        ctk.CTkLabel(card, text="Try another query or relax the filters for source, language, format or rating.", font=ctk.CTkFont(size=14), text_color=_TEXT_MUTED).pack(
            anchor="w", padx=24, pady=(0, 22)
        )

    def _apply_search_filters(self, results: list[BookResult]) -> list[BookResult]:
        source = self.search_source_var.get()
        language = self.search_language_var.get()
        fmt = self.search_format_var.get()
        min_rating = self.search_rating_var.get()
        sort_by = self.search_sort_var.get()

        filtered: list[BookResult] = []
        for book in results:
            if source != "All Sources" and book.source != source:
                continue
            if language == "English" and book.language.lower() != "english":
                continue
            if language == "Turkish" and book.language.lower() != "turkish":
                continue
            if language == "Other" and book.language.lower() in {"english", "turkish", ""}:
                continue
            if fmt != "Any" and not any(link.format.lower() == fmt.lower() for link in book.downloads):
                continue
            if min_rating == "3+" and book.rating < 3.0:
                continue
            if min_rating == "4+" and book.rating < 4.0:
                continue
            filtered.append(book)

        if sort_by == "Rating":
            filtered.sort(key=lambda item: (item.rating, item.ratings_count), reverse=True)
        elif sort_by == "Newest":
            filtered.sort(key=lambda item: int(item.year) if str(item.year).isdigit() else 0, reverse=True)
        elif sort_by == "Title":
            filtered.sort(key=lambda item: item.title.lower())
        return filtered

    def _make_search_card(self, book: BookResult) -> None:
        card = ctk.CTkFrame(self.results_frame.inner, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
        card.pack(fill="x", pady=6, padx=2)

        cover = ctk.CTkLabel(card, text="BOOK", width=104, height=148, fg_color=_CARD_BG, corner_radius=14, text_color=_TEXT_SOFT)
        cover.pack(side="left", padx=(16, 10), pady=16)
        if book.cover_url:
            self._load_cover_async(book.cover_url, cover)

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=8, pady=16)
        ctk.CTkLabel(info, text=book.title, font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT, anchor="w", justify="left", wraplength=520).pack(anchor="w")
        if book.author:
            ctk.CTkLabel(info, text=book.author, font=ctk.CTkFont(size=13), text_color=_TEXT_MUTED, anchor="w").pack(anchor="w", pady=(4, 10))

        badge_row = ctk.CTkFrame(info, fg_color="transparent")
        badge_row.pack(anchor="w", pady=(0, 10))
        for text, color in [
            (book.source, _ACCENT_SOFT),
            (book.language, _CARD_BG),
            (book.year, _SURFACE_ALT),
        ]:
            if text:
                self._make_badge(badge_row, text, color)

        rating_text = f"{_rating_stars(book.rating)}  {book.rating:.1f}  ({book.ratings_count} reviews)" if book.rating > 0 else "No rating metadata available"
        ctk.CTkLabel(info, text=rating_text, font=ctk.CTkFont(size=12), text_color=_WARNING if book.rating > 0 else _TEXT_SOFT, anchor="w").pack(anchor="w")

        if book.description:
            ctk.CTkLabel(
                info,
                text=book.description[:220],
                font=ctk.CTkFont(size=12),
                text_color=_TEXT_MUTED,
                wraplength=560,
                justify="left",
            ).pack(anchor="w", pady=(10, 0))

        if book.subjects:
            subjects = ctk.CTkFrame(info, fg_color="transparent")
            subjects.pack(anchor="w", pady=(10, 0))
            for subject in book.subjects[:4]:
                self._make_badge(subjects, subject, _SURFACE_ALT)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(side="right", padx=16, pady=16)
        for link in book.downloads:
            ctk.CTkButton(
                actions,
                text=f"Download {link.format.upper()}",
                width=172,
                height=36,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOVER,
                corner_radius=12,
                text_color=_TEXT,
                command=lambda dl=link, item=book: self._download_book(dl, item),
            ).pack(pady=4)
            if link.mirror:
                ctk.CTkLabel(actions, text=link.mirror, font=ctk.CTkFont(size=11), text_color=_TEXT_SOFT).pack(pady=(0, 4))
        if not book.downloads:
            ctk.CTkLabel(actions, text="No direct file available", text_color=_TEXT_SOFT).pack()

    def _download_book(self, selected_link: Any, book: BookResult) -> None:
        self._refresh_settings_cache()
        self._set_status(f'Downloading "{book.title}" as {selected_link.format.upper()}...')
        self.update_idletasks()

        ordered_links = [selected_link] + [link for link in book.downloads if link.url != selected_link.url and link.format == selected_link.format]

        def _work() -> tuple[str, str]:
            last_error = "Unknown download error."
            for link in ordered_links:
                response = None
                dest: Path | None = None
                try:
                    urls = [link.url]
                    if "/ads.php?md5=" in link.url:
                        resolved = resolve_external_download(link.url)
                        if resolved:
                            urls = [resolved]
                        else:
                            last_error = "External source could not resolve the direct download link."
                            continue
                    elif "archive.org" in link.url:
                        alt = link.url.replace("//dn", "//ia").replace(".ca.archive.org", ".us.archive.org")
                        if alt != link.url:
                            urls.append(alt)

                    for url in urls:
                        try:
                            response = requests.get(url, stream=True, timeout=60, headers=_UA, allow_redirects=True)
                            if response.status_code >= 400:
                                last_error = f"Server returned status {response.status_code}."
                                response.close()
                                response = None
                                continue
                            content_type = response.headers.get("Content-Type", "")
                            if "text/html" in content_type and link.format in ("epub", "pdf"):
                                last_error = "Received an HTML page instead of a downloadable file."
                                response.close()
                                response = None
                                continue
                            break
                        except requests.RequestException as exc:
                            last_error = str(exc)
                            log_exception("Download request failed")
                            response = None
                    if response is None:
                        continue

                    filename = _safe_filename(book.title, link.format)
                    dest = LIBRARY_DIR / filename
                    index = 1
                    while dest.exists():
                        filename = _safe_filename(f"{book.title}_{index}", link.format)
                        dest = LIBRARY_DIR / filename
                        index += 1
                    with open(dest, "wb") as handle:
                        wrote_data = False
                        for chunk in response.iter_content(8192):
                            if chunk:
                                handle.write(chunk)
                                wrote_data = True
                        if not wrote_data:
                            raise RuntimeError("No file data was received from the source.")
                    collections: list[str] = []
                    default_collection = self.settings.get("default_collection", "").strip()
                    if default_collection:
                        collections = [default_collection]
                    add_to_library(
                        filename,
                        book.title,
                        book.author,
                        link.format,
                        book.cover_url,
                        book.source,
                        language=book.language,
                        year=book.year,
                        rating=book.rating,
                        ratings_count=book.ratings_count,
                        description=book.description,
                        subjects=book.subjects,
                        collections=collections,
                    )
                    record_download_history(
                        title=book.title,
                        author=book.author,
                        source=book.source,
                        fmt=link.format.upper(),
                        status="success",
                        filename=filename,
                        message="Download completed.",
                    )
                    log_info(f"Downloaded book title={book.title!r} format={link.format!r}")
                    return filename, f'"{book.title}" added to the library.'
                except Exception as exc:
                    log_exception("Download pipeline failed")
                    last_error = str(exc)
                    if dest and dest.exists():
                        dest.unlink(missing_ok=True)
                finally:
                    if response is not None:
                        response.close()

            record_download_history(
                title=book.title,
                author=book.author,
                source=book.source,
                fmt=selected_link.format.upper(),
                status="failed",
                message=last_error,
            )
            raise RuntimeError(last_error)

        def _done(_result: tuple[str, str]) -> None:
            _, message = _result
            self._set_status(message)
            if self.settings.get("open_library_after_download", True):
                self._show_library()

        self._run_background(_work, _done, user_error="Download failed.")

    # Library page

    def _show_library(self) -> None:
        self._set_active_nav("library")
        self._clear_content()
        self._refresh_settings_cache()
        self.selected_book_ids = set()
        books = get_all_books()
        self._create_header("Library", "Search, filter and manage downloaded titles with favorites and collections.", "Refresh", self._show_library)
        self._summary_row(self._library_summary_items(books))

        controls = self._make_surface(self.content, (0, 14))
        row = ctk.CTkFrame(controls, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=18)
        self.library_search_var = tk.StringVar()
        self.library_collection_var = tk.StringVar(value="All Collections")
        self.library_format_var = tk.StringVar(value="All Formats")
        self.library_source_var = tk.StringVar(value="All Sources")
        self.library_favorites_var = tk.BooleanVar(value=False)
        self.library_status_var = tk.StringVar(value="All Statuses")
        self.library_view_var = tk.StringVar(value=self.settings.get("library_view", "List"))
        self.library_bulk_mode_var = tk.BooleanVar(value=False)

        search_entry = ctk.CTkEntry(
            row,
            textvariable=self.library_search_var,
            placeholder_text="Search title, author, description or collection",
            height=42,
            corner_radius=14,
            border_color=_CARD_BORDER,
            fg_color=_CARD_BG,
            text_color=_TEXT,
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        search_entry.bind("<KeyRelease>", lambda _event: self._refresh_library_results())

        filter_frame = ctk.CTkFrame(controls, fg_color="transparent")
        filter_frame.pack(fill="x", padx=22, pady=(0, 18))
        self._make_library_filter(filter_frame, "Collection", self.library_collection_var, ["All Collections", *list_collections()])
        self._make_library_filter(filter_frame, "Format", self.library_format_var, ["All Formats", "EPUB", "PDF"])
        sources = sorted({book.get("source", "") for book in books if book.get("source")})
        self._make_library_filter(filter_frame, "Source", self.library_source_var, ["All Sources", *sources])
        self._make_library_filter(filter_frame, "Status", self.library_status_var, ["All Statuses", "Unread", "Reading", "Completed"])
        self._make_library_filter(filter_frame, "View", self.library_view_var, ["List", "Grid"])
        ctk.CTkCheckBox(
            filter_frame,
            text="Favorites only",
            variable=self.library_favorites_var,
            command=self._refresh_library_results,
            text_color=_TEXT,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            border_color=_CARD_BORDER,
        ).pack(side="left", padx=(8, 0), pady=(20, 0))
        ctk.CTkCheckBox(
            filter_frame,
            text="Bulk mode",
            variable=self.library_bulk_mode_var,
            command=self._refresh_library_results,
            text_color=_TEXT,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            border_color=_CARD_BORDER,
        ).pack(side="left", padx=(8, 0), pady=(20, 0))

        bulk_row = ctk.CTkFrame(controls, fg_color="transparent")
        bulk_row.pack(fill="x", padx=22, pady=(0, 18))
        self.bulk_status_label = ctk.CTkLabel(bulk_row, text="0 selected", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT)
        self.bulk_status_label.pack(side="left", padx=(0, 14))
        ctk.CTkButton(bulk_row, text="Favorite Selected", width=138, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=self._bulk_mark_favorite).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bulk_row, text="Set Reading", width=118, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=self._bulk_set_reading).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bulk_row, text="Add Collection", width=122, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=self._bulk_add_collection).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bulk_row, text="Remove Selected", width=132, height=34, fg_color=_DANGER, hover_color=_DANGER_HOVER, text_color=_TEXT, command=self._bulk_remove_books).pack(side="left")

        recommendations = get_recommendations(limit=4)
        if recommendations:
            rec_panel = ctk.CTkFrame(controls, fg_color=_CARD_BG, corner_radius=16, border_width=1, border_color=_CARD_BORDER)
            rec_panel.pack(fill="x", padx=22, pady=(0, 18))
            ctk.CTkLabel(rec_panel, text="Recommended from your library", font=ctk.CTkFont(size=14, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=16, pady=(14, 4))
            rec_row = ctk.CTkFrame(rec_panel, fg_color="transparent")
            rec_row.pack(fill="x", padx=16, pady=(0, 14))
            for book in recommendations:
                self._make_badge(rec_row, book.get("title", "Unknown")[:24], _SURFACE_ALT)

        self.inline_status = ctk.CTkLabel(self.content, text="", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w")
        self.inline_status.pack(fill="x", padx=30, pady=(0, 6))
        self.library_results = ScrollableFrame(self.content, fg_color=_APP_BG)
        self.library_results.pack(fill="both", expand=True, padx=28, pady=(0, 18))
        self._refresh_library_results()

    def _make_library_filter(self, parent: ctk.CTkFrame, label: str, var: tk.StringVar, values: list[str]) -> None:
        group = ctk.CTkFrame(parent, fg_color="transparent")
        group.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(group, text=label, font=ctk.CTkFont(size=11, weight="bold"), text_color=_TEXT_SOFT).pack(anchor="w", pady=(0, 4))
        ctk.CTkOptionMenu(
            group,
            values=values,
            variable=var,
            height=34,
            fg_color=_CARD_BG,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_SURFACE_ALT,
            text_color=_TEXT,
            dropdown_text_color=_TEXT,
            command=lambda _value: self._refresh_library_results(),
        ).pack(fill="x")

    def _refresh_library_results(self) -> None:
        if not hasattr(self, "library_results"):
            return
        for widget in self.library_results.winfo_children():
            widget.destroy()

        collection = self.library_collection_var.get()
        fmt = self.library_format_var.get()
        source = self.library_source_var.get()
        books = search_books_in_library(
            query=self.library_search_var.get().strip(),
            favorites_only=self.library_favorites_var.get(),
            collection="" if collection == "All Collections" else collection,
            fmt="" if fmt == "All Formats" else fmt,
            source="" if source == "All Sources" else source,
        )
        status = self.library_status_var.get()
        if status != "All Statuses":
            books = [book for book in books if book.get("reading_status") == status]
        view = self.library_view_var.get()
        update_settings(library_view=view)
        self._refresh_settings_cache()
        self._update_bulk_status()
        self._set_status(f"{len(books)} library item(s).")

        if not books:
            self._render_library_empty()
            return
        if view == "Grid":
            self._render_library_grid(books)
        else:
            for book in books:
                self._make_library_card(book)

    def _render_library_empty(self) -> None:
        card = ctk.CTkFrame(self.library_results.inner, fg_color=_SURFACE, corner_radius=22, border_width=1, border_color=_CARD_BORDER)
        card.pack(fill="x", padx=2, pady=2)
        ctk.CTkLabel(card, text="No library items match the current view", font=ctk.CTkFont(size=20, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=24, pady=(22, 8))
        ctk.CTkLabel(card, text="Try a broader search, clear one of the filters, or download a new title from Catalog Search.", font=ctk.CTkFont(size=14), text_color=_TEXT_MUTED).pack(
            anchor="w", padx=24, pady=(0, 22)
        )

    def _render_library_grid(self, books: list[dict[str, Any]]) -> None:
        for idx, book in enumerate(books):
            row_idx = idx // 2
            col_idx = idx % 2
            card = ctk.CTkFrame(self.library_results.inner, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
            card.grid(row=row_idx, column=col_idx, padx=8, pady=8, sticky="nsew")
            self.library_results.inner.grid_columnconfigure(col_idx, weight=1)
            if self.library_bulk_mode_var.get():
                selected = tk.BooleanVar(value=book["id"] in self.selected_book_ids)
                ctk.CTkCheckBox(
                    card,
                    text="",
                    variable=selected,
                    command=lambda book_id=book["id"], var=selected: self._toggle_book_selection(book_id, var.get()),
                    fg_color=_ACCENT,
                    hover_color=_ACCENT_HOVER,
                    border_color=_CARD_BORDER,
                    width=20,
                ).pack(anchor="ne", padx=10, pady=(10, 0))
            ctk.CTkLabel(card, text=book.get("title", "Unknown"), font=ctk.CTkFont(size=16, weight="bold"), text_color=_TEXT, wraplength=260, justify="left").pack(anchor="w", padx=16, pady=(8, 4))
            ctk.CTkLabel(card, text=book.get("author", ""), font=ctk.CTkFont(size=12), text_color=_TEXT_MUTED).pack(anchor="w", padx=16)
            ctk.CTkLabel(card, text=book.get("description", "")[:120], font=ctk.CTkFont(size=11), text_color=_TEXT_SOFT, wraplength=260, justify="left").pack(anchor="w", padx=16, pady=(8, 10))
            badges = ctk.CTkFrame(card, fg_color="transparent")
            badges.pack(anchor="w", padx=16, pady=(0, 10))
            for text, color in [
                (book.get("format", "").upper(), _ACCENT_SOFT),
                (book.get("reading_status", ""), _SURFACE_ALT),
            ]:
                if text:
                    self._make_badge(badges, text, color)
            ctk.CTkButton(card, text="Edit", width=90, height=32, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=lambda b=book: self._edit_book_details(b["id"])).pack(anchor="w", padx=16, pady=(0, 16))

    def _make_library_card(self, book: dict[str, Any]) -> None:
        card = ctk.CTkFrame(self.library_results.inner, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
        card.pack(fill="x", pady=6, padx=2)
        if self.library_bulk_mode_var.get():
            selected = tk.BooleanVar(value=book["id"] in self.selected_book_ids)
            ctk.CTkCheckBox(
                card,
                text="",
                variable=selected,
                command=lambda book_id=book["id"], var=selected: self._toggle_book_selection(book_id, var.get()),
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOVER,
                border_color=_CARD_BORDER,
                width=20,
            ).place(x=10, y=16)
        cover = ctk.CTkLabel(card, text="FILE", width=88, height=120, fg_color=_CARD_BG, corner_radius=14, text_color=_TEXT_SOFT)
        cover.pack(side="left", padx=(40 if self.library_bulk_mode_var.get() else 16, 10), pady=16)
        if book.get("cover_url"):
            self._load_cover_async(book["cover_url"], cover, (82, 118))

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=8, pady=16)
        title_row = ctk.CTkFrame(info, fg_color="transparent")
        title_row.pack(fill="x")
        ctk.CTkLabel(title_row, text=book.get("title", "Unknown"), font=ctk.CTkFont(size=17, weight="bold"), text_color=_TEXT, anchor="w", wraplength=450).pack(side="left", anchor="w")
        ctk.CTkButton(
            title_row,
            text="★" if book.get("favorite") else "☆",
            width=34,
            height=30,
            corner_radius=12,
            fg_color=_SURFACE_ALT,
            hover_color=_CARD_BG,
            text_color=_WARNING,
            command=lambda book_id=book["id"]: self._toggle_favorite_and_refresh(book_id),
        ).pack(side="right")

        if book.get("author"):
            ctk.CTkLabel(info, text=book["author"], font=ctk.CTkFont(size=13), text_color=_TEXT_MUTED, anchor="w").pack(anchor="w", pady=(4, 8))
        if book.get("description"):
            ctk.CTkLabel(info, text=book["description"][:180], font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, wraplength=520, justify="left").pack(anchor="w", pady=(0, 8))

        badges = ctk.CTkFrame(info, fg_color="transparent")
        badges.pack(anchor="w")
        for text, color in [
            (book.get("format", "").upper(), _ACCENT_SOFT),
            (book.get("source", ""), _SURFACE_ALT),
            (book.get("language", ""), _CARD_BG),
            (book.get("reading_status", ""), _SUCCESS if book.get("reading_status") == "Completed" else _SURFACE_ALT),
        ]:
            if text:
                self._make_badge(badges, text, color)
        for collection in book.get("collections", [])[:3]:
            self._make_badge(badges, collection, _SUCCESS)
        for tag in book.get("tags", [])[:2]:
            self._make_badge(badges, f"#{tag}", _CARD_BG)

        if book.get("notes"):
            ctk.CTkLabel(info, text=f'Notes: {book.get("notes", "")[:90]}', font=ctk.CTkFont(size=11), text_color=_TEXT_SOFT, wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))
        ctk.CTkLabel(info, text=book.get("filename", ""), font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w").pack(anchor="w", pady=(6, 0))

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(side="right", padx=16, pady=16)
        for text, cmd, fg, hover in [
            ("Edit", lambda b=book: self._edit_book_details(b["id"]), _SURFACE_ALT, _CARD_BG),
            ("Open File", lambda b=book: self._open_book_file(b), _ACCENT, _ACCENT_HOVER),
            ("Collections", lambda b=book: self._edit_collections(b["id"]), _SURFACE_ALT, _CARD_BG),
            ("Send to Device", lambda b=book: self._send_to_device(b), _SURFACE_ALT, _CARD_BG),
            ("Remove", lambda b=book: self._delete_book(b), _DANGER, _DANGER_HOVER),
        ]:
            ctk.CTkButton(
                actions,
                text=text,
                width=136,
                height=34,
                fg_color=fg,
                hover_color=hover,
                corner_radius=12,
                border_width=1 if fg == _SURFACE_ALT else 0,
                border_color=_CARD_BORDER,
                text_color=_TEXT,
                command=cmd,
            ).pack(pady=4)

    def _toggle_book_selection(self, book_id: str, selected: bool) -> None:
        if selected:
            self.selected_book_ids.add(book_id)
        else:
            self.selected_book_ids.discard(book_id)
        self._update_bulk_status()

    def _update_bulk_status(self) -> None:
        if hasattr(self, "bulk_status_label"):
            self.bulk_status_label.configure(text=f"{len(self.selected_book_ids)} selected")

    def _edit_book_details(self, book_id: str) -> None:
        book = get_book(book_id)
        if not book:
            self._set_status("Book not found.")
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("Edit Book Details")
        dialog.geometry("640x620")
        dialog.configure(fg_color=_SURFACE)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Edit metadata", font=ctk.CTkFont(size=22, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=22, pady=(20, 10))
        body = ctk.CTkFrame(dialog, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))

        title_var = tk.StringVar(value=book.get("title", ""))
        author_var = tk.StringVar(value=book.get("author", ""))
        status_var = tk.StringVar(value=book.get("reading_status", "Unread"))
        tags_var = tk.StringVar(value=", ".join(book.get("tags", [])))

        self._make_settings_field(body, "Title", ctk.CTkEntry(body, textvariable=title_var, fg_color=_CARD_BG, border_color=_CARD_BORDER, text_color=_TEXT))
        self._make_settings_field(body, "Author", ctk.CTkEntry(body, textvariable=author_var, fg_color=_CARD_BG, border_color=_CARD_BORDER, text_color=_TEXT))
        self._make_settings_field(body, "Reading status", ctk.CTkOptionMenu(
            body,
            values=["Unread", "Reading", "Completed"],
            variable=status_var,
            fg_color=_CARD_BG,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_SURFACE_ALT,
            text_color=_TEXT,
            dropdown_text_color=_TEXT,
        ))
        self._make_settings_field(body, "Tags", ctk.CTkEntry(body, textvariable=tags_var, fg_color=_CARD_BG, border_color=_CARD_BORDER, text_color=_TEXT))
        ctk.CTkLabel(body, text="Description", font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT).pack(anchor="w", pady=(8, 4))
        description_box = ctk.CTkTextbox(body, height=120, fg_color=_CARD_BG, text_color=_TEXT, border_width=1, border_color=_CARD_BORDER)
        description_box.pack(fill="x")
        description_box.insert("1.0", book.get("description", ""))
        ctk.CTkLabel(body, text="Notes", font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT).pack(anchor="w", pady=(12, 4))
        notes_box = ctk.CTkTextbox(body, height=120, fg_color=_CARD_BG, text_color=_TEXT, border_width=1, border_color=_CARD_BORDER)
        notes_box.pack(fill="x")
        notes_box.insert("1.0", book.get("notes", ""))
        tag_hint = ", ".join(list_tags()[:8])
        if tag_hint:
            ctk.CTkLabel(body, text=f"Existing tags: {tag_hint}", font=ctk.CTkFont(size=11), text_color=_TEXT_SOFT).pack(anchor="w", pady=(6, 0))

        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(fill="x", padx=22, pady=(0, 20))

        def _save() -> None:
            try:
                update_book(
                    book_id,
                    title=title_var.get().strip() or book.get("title", ""),
                    author=author_var.get().strip(),
                    description=description_box.get("1.0", "end").strip(),
                )
                set_reading_status(book_id, status_var.get())
                set_book_notes_and_tags(
                    book_id,
                    notes_box.get("1.0", "end").strip(),
                    [item.strip() for item in tags_var.get().split(",") if item.strip()],
                )
                log_info(f"Metadata updated for book_id={book_id}")
                dialog.destroy()
                self._refresh_library_results()
                self._set_status("Book metadata updated.")
            except Exception:
                log_exception("Book metadata update failed")
                self._set_status("Book metadata update failed. Check the log for details.")

        ctk.CTkButton(actions, text="Cancel", width=100, height=36, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=dialog.destroy).pack(side="right")
        ctk.CTkButton(actions, text="Save", width=100, height=36, fg_color=_ACCENT, hover_color=_ACCENT_HOVER, text_color=_TEXT, command=_save).pack(side="right", padx=(0, 10))

    def _bulk_mark_favorite(self) -> None:
        if not self.selected_book_ids:
            self._set_status("Select at least one book in bulk mode.")
            return
        try:
            count = apply_bulk_update(list(self.selected_book_ids), favorite=True)
            log_info(f"Bulk favorite applied count={count}")
            self._set_status(f"{count} book(s) marked as favorite.")
            self._refresh_library_results()
        except Exception:
            log_exception("Bulk favorite failed")
            self._set_status("Bulk favorite failed. Check the log for details.")

    def _bulk_set_reading(self) -> None:
        if not self.selected_book_ids:
            self._set_status("Select at least one book in bulk mode.")
            return
        dialog = ctk.CTkInputDialog(text="Enter reading status: Unread, Reading, or Completed", title="Bulk Reading Status")
        value = dialog.get_input()
        if value is None:
            return
        status = value.strip().title()
        if status not in {"Unread", "Reading", "Completed"}:
            self._set_status("Invalid status. Use Unread, Reading, or Completed.")
            return
        try:
            count = apply_bulk_update(list(self.selected_book_ids), reading_status=status)
            log_info(f"Bulk reading status update count={count} status={status}")
            self._set_status(f"{count} book(s) updated to {status}.")
            self._refresh_library_results()
        except Exception:
            log_exception("Bulk reading status failed")
            self._set_status("Bulk reading status failed. Check the log for details.")

    def _bulk_add_collection(self) -> None:
        if not self.selected_book_ids:
            self._set_status("Select at least one book in bulk mode.")
            return
        dialog = ctk.CTkInputDialog(text="Collection name to add to selected books", title="Bulk Collection")
        value = dialog.get_input()
        if value is None or not value.strip():
            return
        try:
            count = apply_bulk_update(list(self.selected_book_ids), collection=value.strip())
            log_info(f"Bulk collection update count={count} collection={value.strip()!r}")
            self._set_status(f'Collection "{value.strip()}" added to {count} book(s).')
            self._refresh_library_results()
        except Exception:
            log_exception("Bulk collection update failed")
            self._set_status("Bulk collection update failed. Check the log for details.")

    def _bulk_remove_books(self) -> None:
        if not self.selected_book_ids:
            self._set_status("Select at least one book in bulk mode.")
            return
        try:
            count = delete_books(list(self.selected_book_ids))
            log_info(f"Bulk delete count={count}")
            self.selected_book_ids.clear()
            self._set_status(f"{count} book(s) removed.")
            self._refresh_library_results()
        except Exception:
            log_exception("Bulk delete failed")
            self._set_status("Bulk delete failed. Check the log for details.")

    def _toggle_favorite_and_refresh(self, book_id: str) -> None:
        try:
            updated = toggle_favorite(book_id)
            if updated:
                self._set_status(f'Favorite updated for "{updated.get("title", "Unknown")}".')
            self._refresh_library_results()
        except Exception:
            log_exception("Favorite toggle failed")
            self._set_status("Favorite update failed. Check the log for details.")

    def _edit_collections(self, book_id: str) -> None:
        book = get_book(book_id)
        if not book:
            self._set_status("Book not found.")
            return
        current = ", ".join(book.get("collections", []))
        dialog = ctk.CTkInputDialog(
            text="Enter collection names separated by commas.",
            title=f'Collections: {book.get("title", "Unknown")}',
        )
        dialog.entry.insert(0, current)
        raw = dialog.get_input()
        if raw is None:
            return
        try:
            collections = [item.strip() for item in raw.split(",") if item.strip()]
            set_book_collections(book_id, collections)
            self._refresh_library_results()
            self._set_status("Collections updated.")
        except Exception:
            log_exception("Collection update failed")
            self._set_status("Collection update failed. Check the log for details.")

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

        ctk.CTkLabel(dialog, text="Remove this title from the library?", font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=22, pady=(22, 8))
        ctk.CTkLabel(dialog, text=book.get("title", "Unknown"), font=ctk.CTkFont(size=14), text_color=_TEXT_MUTED, wraplength=360, justify="left").pack(anchor="w", padx=22, pady=(0, 18))

        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(anchor="e", padx=22, pady=(0, 18))

        def _confirm() -> None:
            try:
                remove_from_library(book["id"])
                dialog.destroy()
                self._refresh_library_results()
                self._set_status(f'"{book.get("title", "Unknown")}" removed from the library.')
            except Exception:
                log_exception("Library delete failed")
                self._set_status("Book removal failed. Check the log for details.")

        ctk.CTkButton(actions, text="Cancel", fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, corner_radius=12, width=100, text_color=_TEXT, command=dialog.destroy).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="Remove", fg_color=_DANGER, hover_color=_DANGER_HOVER, corner_radius=12, width=100, text_color=_TEXT, command=_confirm).pack(side="left")

    # History page

    def _show_history(self) -> None:
        self._set_active_nav("history")
        self._clear_content()
        history = get_download_history()
        self._create_header("Download History", "Review successful and failed download attempts with timestamps and messages.", "Refresh", self._show_history)
        self._summary_row(self._history_summary_items(history))
        self.inline_status = ctk.CTkLabel(self.content, text=f"{len(history)} history event(s).", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w")
        self.inline_status.pack(fill="x", padx=30, pady=(0, 6))

        if not history:
            self._show_empty_state("No download history yet", "Every download success or failure will appear here so you can quickly inspect what happened.")
            return

        scroll = ScrollableFrame(self.content, fg_color=_APP_BG)
        scroll.pack(fill="both", expand=True, padx=28, pady=(0, 18))
        for entry in history:
            card = ctk.CTkFrame(scroll.inner, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
            card.pack(fill="x", padx=2, pady=6)
            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(side="left", fill="both", expand=True, padx=18, pady=16)
            ctk.CTkLabel(left, text=entry.get("title", "Unknown"), font=ctk.CTkFont(size=17, weight="bold"), text_color=_TEXT).pack(anchor="w")
            ctk.CTkLabel(left, text=f'{entry.get("timestamp", "")}  |  {entry.get("source", "")}  |  {entry.get("format", "")}', font=ctk.CTkFont(size=12), text_color=_TEXT_MUTED).pack(anchor="w", pady=(4, 8))
            if entry.get("message"):
                ctk.CTkLabel(left, text=entry["message"], font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, wraplength=780, justify="left").pack(anchor="w")
            badge = ctk.CTkFrame(card, fg_color="transparent")
            badge.pack(side="right", padx=18, pady=16)
            self._make_badge(badge, entry.get("status", "unknown").upper(), _SUCCESS if entry.get("status") == "success" else _DANGER)

    # Devices page

    def _show_devices(self) -> None:
        self._set_active_nav("devices")
        self._clear_content()
        devices = detect_devices()
        transfers = get_transfer_history(limit=6)
        self._create_header("Devices", "Review connected reading devices, install MTP support and run connection diagnostics.", "Scan", self._show_devices)
        self._summary_row(self._device_summary_items(devices))
        self.inline_status = ctk.CTkLabel(self.content, text="Connection scan complete.", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w")
        self.inline_status.pack(fill="x", padx=30, pady=(0, 6))

        if not devices:
            self._show_empty_state(
                "No devices detected",
                "Verify that the device is unlocked, connected with a data cable, and trusted by the computer. If your Kindle uses MTP, install the required support package.",
            )
            action_row = ctk.CTkFrame(self.content, fg_color="transparent")
            action_row.pack(fill="x", padx=28, pady=(0, 20))
            ctk.CTkButton(action_row, text="Install MTP Support", width=180, height=38, fg_color=_ACCENT, hover_color=_ACCENT_HOVER, corner_radius=14, text_color=_TEXT, command=self._install_mtp).pack(side="left", padx=(0, 10))
            ctk.CTkButton(action_row, text="Run USB Diagnostics", width=180, height=38, fg_color=_SURFACE, hover_color=_SURFACE_ALT, border_width=1, border_color=_CARD_BORDER, corner_radius=14, text_color=_TEXT, command=self._run_usb_troubleshoot).pack(side="left")
            self._set_status("No device detected.")
            return

        scroll = ScrollableFrame(self.content, fg_color=_APP_BG)
        scroll.pack(fill="both", expand=True, padx=28, pady=(0, 18))
        kind_map = {"ereader": "E-Reader", "ipad": "Tablet / Phone", "mtp": "E-Reader (MTP)"}
        self._set_status(f"{len(devices)} device(s) detected.")
        for device in devices:
            card = ctk.CTkFrame(scroll.inner, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
            card.pack(fill="x", padx=2, pady=6)
            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(side="left", fill="both", expand=True, padx=18, pady=16)
            ctk.CTkLabel(left, text=device.name, font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT).pack(anchor="w")
            ctk.CTkLabel(left, text=kind_map.get(device.kind, "USB Storage"), font=ctk.CTkFont(size=13), text_color=_TEXT_MUTED).pack(anchor="w", pady=(4, 10))
            badges = ctk.CTkFrame(left, fg_color="transparent")
            badges.pack(anchor="w", pady=(0, 10))
            self._make_badge(badges, kind_map.get(device.kind, "USB Storage"), _ACCENT_SOFT)
            self._make_badge(badges, "Mounted" if device.mount_point else "Manual", _SUCCESS if device.mount_point or device.kind == "mtp" else _SURFACE_ALT)
            ctk.CTkLabel(left, text=device.mount_point or "No direct mount point available", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, wraplength=720, justify="left").pack(anchor="w")
            if device.status:
                ctk.CTkLabel(left, text=device.status, font=ctk.CTkFont(size=12), text_color=_WARNING, wraplength=720, justify="left").pack(anchor="w", pady=(8, 0))

        if transfers:
            section = ctk.CTkFrame(scroll.inner, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
            section.pack(fill="x", padx=2, pady=(18, 6))
            ctk.CTkLabel(section, text="Recent transfer history", font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=18, pady=(16, 10))
            for entry in transfers:
                row = ctk.CTkFrame(section, fg_color="transparent")
                row.pack(fill="x", padx=18, pady=4)
                ctk.CTkLabel(row, text=f'{entry.get("timestamp", "")}  |  {entry.get("title", "")}', font=ctk.CTkFont(size=12), text_color=_TEXT_MUTED).pack(side="left")
                self._make_badge(row, entry.get("status", "unknown").upper(), _SUCCESS if entry.get("status") == "success" else _DANGER)

    def _install_mtp(self) -> None:
        import shutil as _shutil

        if not _shutil.which("brew"):
            self._set_status("Homebrew not found. Install Homebrew first to add MTP support.")
            return
        self._set_status("Installing MTP support via Homebrew...")
        self.update_idletasks()

        def _work() -> None:
            subprocess.run(["brew", "install", "libmtp"], capture_output=True, timeout=120, check=False)

        self._run_background(_work, lambda _result: self._set_status("MTP support installed. Run a new device scan."), user_error="MTP installation failed.")

    def _run_usb_troubleshoot(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("USB Diagnostics")
        dialog.geometry("620x500")
        dialog.configure(fg_color=_APP_BG)
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="USB Diagnostics", font=ctk.CTkFont(size=22, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=20, pady=(18, 6))
        result_text = ctk.CTkTextbox(dialog, fg_color=_SURFACE, text_color=_TEXT, font=ctk.CTkFont(family="Menlo", size=12), corner_radius=16, wrap="word")
        result_text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        result_text.insert("end", "Running diagnostics...\n")
        dialog.update_idletasks()

        def _work() -> str:
            lines: list[str] = []
            try:
                out = subprocess.check_output(["system_profiler", "SPUSBDataType", "-detailLevel", "mini"], text=True, timeout=5)
                usb_devices = [
                    line.strip().rstrip(":")
                    for line in out.splitlines()
                    if line.strip().endswith(":") and ":" not in line.strip()[:-1] and "USB" not in line.strip() and "Host" not in line.strip()
                ]
                lines.append(f"[OK] USB devices: {', '.join(usb_devices)}" if usb_devices else "[WARN] No USB devices were listed.")
            except Exception:
                log_exception("USB diagnostics system_profiler failed")
                lines.append("[WARN] Could not scan USB devices with system_profiler.")

            try:
                volumes = [volume.name for volume in Path("/Volumes").iterdir() if volume.is_dir()]
                lines.append(f"[OK] Mounted volumes: {', '.join(volumes)}" if volumes else "[WARN] No mounted external volumes.")
            except Exception:
                log_exception("USB diagnostics volume scan failed")
                lines.append("[WARN] Could not inspect mounted volumes.")

            lines.append("")
            lines.append("Recommended next steps:")
            lines.append("1. Use a verified data cable and connect directly to the computer.")
            lines.append("2. Unlock the reader and accept any USB trust prompt.")
            lines.append("3. If the device is new firmware Kindle, install libmtp.")
            return "\n".join(lines)

        def _done(report: str) -> None:
            result_text.delete("1.0", "end")
            result_text.insert("end", report)

        self._run_background(_work, _done, user_error="USB diagnostics failed.")

    # Transfer helpers

    def _send_to_device(self, book: dict[str, Any]) -> None:
        devices = detect_devices()
        if not devices:
            self._set_status("No device detected. Open the Devices section to troubleshoot the connection.")
            return
        if len(devices) == 1:
            self._do_transfer(book, devices[0])
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Device")
        dialog.geometry("420x340")
        dialog.configure(fg_color=_SURFACE)
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="Select target device", font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=22, pady=(20, 8))
        for device in devices:
            kind = {"ipad": "Tablet", "ereader": "E-Reader", "mtp": "E-Reader (MTP)"}.get(device.kind, "USB")
            ctk.CTkButton(
                dialog,
                text=f"{device.name}  |  {kind}",
                height=40,
                fg_color=_CARD_BG,
                hover_color=_SURFACE_ALT,
                corner_radius=12,
                border_width=1,
                border_color=_CARD_BORDER,
                text_color=_TEXT,
                command=lambda dev=device: (dialog.destroy(), self._do_transfer(book, dev)),
            ).pack(fill="x", padx=22, pady=4)

    def _do_transfer(self, book: dict[str, Any], device: Any) -> None:
        path = get_book_path(book["id"])
        if not path:
            self._set_status("File not found in library.")
            return
        subdir = self.settings.get("device_subdir", "").strip()
        try:
            result = copy_to_device(str(path), device, subdir=subdir)
            record_transfer_history(title=book.get("title", "Unknown"), device_name=device.name, status="success", message=result)
            log_info(f'Transfer completed book={book.get("title", "")!r} device={device.name!r}')
            self._set_status(f'Transfer completed to {device.name}. {result}')
        except Exception as exc:
            record_transfer_history(title=book.get("title", "Unknown"), device_name=device.name, status="failed", message=str(exc))
            log_exception("Device transfer failed")
            self._set_status(f"Transfer failed: {exc}")

    # Settings page

    def _show_settings(self) -> None:
        self._set_active_nav("settings")
        self._clear_content()
        self._refresh_settings_cache()
        self._create_header("Settings", "Configure preferred formats, source defaults, transfer behavior and logging access.")
        self._summary_row(
            [
                ("Preferred Format", self.settings.get("preferred_format", "Any")),
                ("Preferred Source", self.settings.get("preferred_source", "All Sources")),
                ("Log File", LOG_FILE.name),
            ]
        )

        panel = self._make_surface(self.content, (0, 16))
        self.settings_format_var = tk.StringVar(value=self.settings.get("preferred_format", "Any"))
        self.settings_source_var = tk.StringVar(value=self.settings.get("preferred_source", "All Sources"))
        self.settings_collection_var = tk.StringVar(value=self.settings.get("default_collection", ""))
        self.settings_device_subdir_var = tk.StringVar(value=self.settings.get("device_subdir", ""))
        self.settings_open_library_var = tk.BooleanVar(value=bool(self.settings.get("open_library_after_download", True)))

        form = ctk.CTkFrame(panel, fg_color="transparent")
        form.pack(fill="x", padx=22, pady=22)
        self._make_settings_field(form, "Preferred download format", ctk.CTkOptionMenu(
            form,
            values=["Any", "EPUB", "PDF"],
            variable=self.settings_format_var,
            fg_color=_CARD_BG,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_SURFACE_ALT,
            text_color=_TEXT,
            dropdown_text_color=_TEXT,
        ))
        self._make_settings_field(form, "Preferred source", ctk.CTkOptionMenu(
            form,
            values=["All Sources", "Project Gutenberg", "Open Library", "External"],
            variable=self.settings_source_var,
            fg_color=_CARD_BG,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_SURFACE_ALT,
            text_color=_TEXT,
            dropdown_text_color=_TEXT,
        ))
        self._make_settings_field(form, "Default collection after download", ctk.CTkEntry(
            form,
            textvariable=self.settings_collection_var,
            fg_color=_CARD_BG,
            border_color=_CARD_BORDER,
            text_color=_TEXT,
        ))
        self._make_settings_field(form, "Device subfolder", ctk.CTkEntry(
            form,
            textvariable=self.settings_device_subdir_var,
            fg_color=_CARD_BG,
            border_color=_CARD_BORDER,
            text_color=_TEXT,
        ))

        ctk.CTkCheckBox(
            panel,
            text="Open Library after a successful download",
            variable=self.settings_open_library_var,
            text_color=_TEXT,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            border_color=_CARD_BORDER,
        ).pack(anchor="w", padx=22, pady=(0, 18))

        action_row = ctk.CTkFrame(panel, fg_color="transparent")
        action_row.pack(fill="x", padx=22, pady=(0, 22))
        ctk.CTkButton(action_row, text="Save Settings", width=150, height=38, fg_color=_ACCENT, hover_color=_ACCENT_HOVER, corner_radius=14, text_color=_TEXT, command=self._save_settings).pack(side="left", padx=(0, 10))
        ctk.CTkButton(action_row, text="Open Log File", width=140, height=38, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, corner_radius=14, text_color=_TEXT, command=self._open_log_file).pack(side="left")

        self.inline_status = ctk.CTkLabel(self.content, text=f"Log file: {LOG_FILE}", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w")
        self.inline_status.pack(fill="x", padx=30, pady=(0, 6))

    def _make_settings_field(self, parent: ctk.CTkFrame, label: str, widget: Any) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=8)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT, width=220, anchor="w").pack(side="left")
        widget.pack(side="left", fill="x", expand=True)

    def _save_settings(self) -> None:
        try:
            update_settings(
                preferred_format=self.settings_format_var.get(),
                preferred_source=self.settings_source_var.get(),
                default_collection=self.settings_collection_var.get().strip(),
                device_subdir=self.settings_device_subdir_var.get().strip(),
                open_library_after_download=bool(self.settings_open_library_var.get()),
            )
            self._refresh_settings_cache()
            self._set_status("Settings saved.")
        except Exception:
            log_exception("Settings save failed")
            self._set_status("Settings save failed. Check the log for details.")

    def _open_log_file(self) -> None:
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", "-R", str(LOG_FILE)])
            elif platform.system() == "Linux":
                subprocess.Popen(["xdg-open", str(LOG_FILE.parent)])
            else:
                subprocess.Popen(["explorer", str(LOG_FILE.parent)])
        except Exception:
            log_exception("Open log file failed")
            self._set_status("Could not open the log file location.")


if __name__ == "__main__":
    AutoBookApp().mainloop()
