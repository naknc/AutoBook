#!/usr/bin/env python3
"""AutoBook desktop workspace. Run with: uv run main.py"""

from __future__ import annotations

import io
import platform
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk
import requests
from PIL import Image

from app.devices import copy_to_device, detect_devices
from app.document_tools import convert_book_format, convert_books, export_library_web_preview, repair_book_file, run_ocr_for_book, run_ocr_for_books
from app.library import (
    LIBRARY_DIR,
    add_to_library,
    apply_bulk_update,
    cancel_download_job,
    clear_finished_queue_jobs,
    clear_search_cache,
    delete_books,
    enqueue_download_job,
    export_library_snapshot,
    get_all_books,
    get_library_analytics,
    get_book,
    get_book_path,
    get_device_profiles,
    get_download_history,
    get_download_queue,
    import_library_snapshot,
    generate_companion_feed,
    get_recommendations,
    get_search_cache_stats,
    get_settings,
    get_transfer_history,
    get_usage_events,
    get_optional_tooling,
    get_next_queued_job,
    list_local_plugins,
    list_collections,
    list_tags,
    load_search_cache,
    organize_library_files,
    record_usage_event,
    save_device_profile,
    save_search_cache,
    scan_library_health,
    reorder_download_job,
    record_download_history,
    record_transfer_history,
    remove_from_library,
    retry_download_job,
    search_books_in_library,
    set_book_collections,
    set_book_notes_and_tags,
    set_reading_status,
    toggle_favorite,
    update_book,
    update_download_job,
    update_settings,
    delete_device_profile,
    import_plugin_manifest,
    toggle_plugin_enabled,
)
from app.ai_tools import ai_enrich_book, ai_generate_search_suggestions, ai_generate_tags, ai_is_configured
from app.logging_utils import LOG_FILE, log_exception, log_info, setup_logging
from app.search import BookResult, book_result_from_dict, book_result_to_dict, download_link_from_dict, resolve_external_download, search_books

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

_THEME_PRESETS = {
    "Corporate Blue": {
        "_NAV_BG": "#0F172A",
        "_APP_BG": "#0B1220",
        "_SURFACE": "#111827",
        "_SURFACE_ALT": "#1F2937",
        "_CARD_BG": "#162033",
        "_CARD_BORDER": "#273449",
        "_TEXT": "#E5EEF9",
        "_TEXT_MUTED": "#93A4BC",
        "_TEXT_SOFT": "#6F839E",
        "_ACCENT": "#2F6FED",
        "_ACCENT_HOVER": "#275DCA",
        "_ACCENT_SOFT": "#17305F",
    },
    "Slate Green": {
        "_NAV_BG": "#101A18",
        "_APP_BG": "#0A1211",
        "_SURFACE": "#13201D",
        "_SURFACE_ALT": "#1B2B27",
        "_CARD_BG": "#18312A",
        "_CARD_BORDER": "#2A443D",
        "_TEXT": "#E7F3EF",
        "_TEXT_MUTED": "#9BB9AF",
        "_TEXT_SOFT": "#729086",
        "_ACCENT": "#2F8F6B",
        "_ACCENT_HOVER": "#277558",
        "_ACCENT_SOFT": "#184438",
    },
}

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}

_I18N = {
    "English": {
        "Catalog Search": "Catalog Search",
        "Library": "Library",
        "Download History": "Download History",
        "Analytics": "Analytics",
        "Devices": "Devices",
        "Settings": "Settings",
        "Trending titles": "Trending titles",
        "Auto categories": "Auto categories",
        "Recent usage events": "Recent usage events",
        "Interface language": "Interface language",
        "Enable local usage telemetry": "Enable local usage telemetry",
        "Open File": "Open File",
        "Send to Device": "Send to Device",
        "Remove": "Remove",
        "Edit": "Edit",
        "Repair": "Repair",
        "Run OCR": "Run OCR",
        "Convert": "Convert",
        "AI Enrich": "AI Enrich",
        "Library Health Scan": "Library Health Scan",
        "Search": "Search",
        "Filters": "Filters",
        "Advanced Filters": "Advanced Filters",
        "AI Suggestions": "AI Suggestions",
        "Favorites only": "Favorites only",
        "Bulk mode": "Bulk mode",
        "Favorite Selected": "Favorite Selected",
        "Set Reading": "Set Reading",
        "Add Collection": "Add Collection",
        "Batch OCR": "Batch OCR",
        "Batch Convert": "Batch Convert",
        "Remove Selected": "Remove Selected",
        "Download queue": "Download queue",
        "Run Queue": "Run Queue",
        "Clear Finished": "Clear Finished",
        "Allowed sources": "Allowed sources",
        "Allowed formats": "Allowed formats",
        "Allowed actions": "Allowed actions",
        "Device profiles": "Device profiles",
        "Save Settings": "Save Settings",
        "Open Log File": "Open Log File",
        "Export Snapshot": "Export Snapshot",
        "Import Snapshot": "Import Snapshot",
        "Run Organize": "Run Organize",
        "Health Scan": "Health Scan",
        "Companion Feed": "Companion Feed",
        "Clear Cache": "Clear Cache",
        "Web Preview": "Web Preview",
        "Import Plugin": "Import Plugin",
        "Add Profile": "Add Profile",
        "Delete Profile": "Delete Profile",
        "Refresh": "Refresh",
    },
    "Turkish": {
        "Catalog Search": "Katalog Arama",
        "Library": "Kütüphane",
        "Download History": "İndirme Geçmişi",
        "Analytics": "Analitik",
        "Devices": "Cihazlar",
        "Settings": "Ayarlar",
        "Trending titles": "Öne çıkan kitaplar",
        "Auto categories": "Otomatik kategoriler",
        "Recent usage events": "Son kullanım olayları",
        "Interface language": "Arayüz dili",
        "Enable local usage telemetry": "Yerel kullanım telemetrisini etkinleştir",
        "Open File": "Dosyayı Aç",
        "Send to Device": "Cihaza Gönder",
        "Remove": "Kaldır",
        "Edit": "Düzenle",
        "Repair": "Onar",
        "Run OCR": "OCR Çalıştır",
        "Convert": "Dönüştür",
        "AI Enrich": "AI Zenginleştir",
        "Library Health Scan": "Kütüphane Sağlık Taraması",
        "Search": "Ara",
        "Filters": "Filtreler",
        "Advanced Filters": "Gelişmiş Filtreler",
        "AI Suggestions": "AI Önerileri",
        "Favorites only": "Sadece favoriler",
        "Bulk mode": "Toplu işlem modu",
        "Favorite Selected": "Seçileni Favorile",
        "Set Reading": "Okuma Durumu Ver",
        "Add Collection": "Koleksiyon Ekle",
        "Batch OCR": "Toplu OCR",
        "Batch Convert": "Toplu Dönüştür",
        "Remove Selected": "Seçileni Kaldır",
        "Download queue": "İndirme kuyruğu",
        "Run Queue": "Kuyruğu Çalıştır",
        "Clear Finished": "Bitenleri Temizle",
        "Allowed sources": "İzin verilen kaynaklar",
        "Allowed formats": "İzin verilen formatlar",
        "Allowed actions": "İzin verilen aksiyonlar",
        "Device profiles": "Cihaz profilleri",
        "Save Settings": "Ayarları Kaydet",
        "Open Log File": "Log Dosyasını Aç",
        "Export Snapshot": "Anlık Görüntü Dışa Aktar",
        "Import Snapshot": "Anlık Görüntü İçe Aktar",
        "Run Organize": "Düzenlemeyi Çalıştır",
        "Health Scan": "Sağlık Taraması",
        "Companion Feed": "Companion Feed",
        "Clear Cache": "Önbelleği Temizle",
        "Web Preview": "Web Önizleme",
        "Import Plugin": "Plugin İçe Aktar",
        "Add Profile": "Profil Ekle",
        "Delete Profile": "Profili Sil",
        "Refresh": "Yenile",
    },
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
    """Canvas-based scrollable container with explicit trackpad routing."""

    _instances: list["ScrollableFrame"] = []
    _bindings_installed = False

    def __init__(self, master, fg_color=_APP_BG, **kwargs):
        super().__init__(master, bg=fg_color, **kwargs)
        self._canvas = tk.Canvas(
            self,
            bg=fg_color,
            cursor="arrow",
            borderwidth=0,
            highlightthickness=0,
        )
        self._scrollbar = tk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")

        self.inner = tk.Frame(self._canvas, bg=fg_color)
        self._window_id = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self.inner.bind("<Configure>", self._on_inner_configure)
        ScrollableFrame._instances.append(self)
        self._install_global_bindings()

    def winfo_children(self):
        return self.inner.winfo_children()

    def _on_canvas_configure(self, event=None):
        width = self._canvas.winfo_width()
        if width > 10:
            self._canvas.itemconfigure(self._window_id, width=width)
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_inner_configure(self, _event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

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

    def _owns_widget(self, widget: tk.Misc | None) -> bool:
        current = widget
        while current is not None:
            if current in {self, self._canvas, self.inner}:
                return True
            current = current.master
        return False

    @classmethod
    def _dispatch_scroll(cls, event) -> str | None:
        root = tk._get_default_root()
        if root is None:
            return None
        widget = root.winfo_containing(root.winfo_pointerx(), root.winfo_pointery()) or event.widget
        for instance in list(cls._instances):
            if not instance.winfo_exists():
                try:
                    cls._instances.remove(instance)
                except ValueError:
                    pass
                continue
            if instance._owns_widget(widget):
                return instance._on_mousewheel(event)
        return None

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
                    delta = -max(1, min(12, abs(raw_delta)))
                    if raw_delta < 0:
                        delta = abs(delta)
                else:
                    delta = -max(1, min(8, abs(raw_delta) // 120 or 1)) if raw_delta > 0 else max(1, min(8, abs(raw_delta) // 120 or 1))
            self._canvas.yview_scroll(delta, "units")
        except Exception:
            log_exception("Trackpad scroll dispatch failed")
        return "break"


class AutoBookApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.logger = setup_logging()
        self.settings = get_settings()
        self._apply_theme_preset(self.settings.get("theme_preset", "Corporate Blue"))

        self.title("AutoBook Workspace")
        self.geometry("1280x860")
        self.minsize(1020, 680)
        self.configure(fg_color=_APP_BG)

        self._image_refs: list[ctk.CTkImage] = []
        self.inline_status: ctk.CTkLabel | None = None
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.current_search_results: list[BookResult] = []
        self.selected_book_ids: set[str] = set()
        self.queue_processing = False
        self._build_shell()
        self.after(150, self._show_onboarding_if_needed)
        self._show_search()

    def _t(self, text: str) -> str:
        language = self.settings.get("interface_language", "English")
        return _I18N.get(language, {}).get(text, text)

    def _apply_theme_preset(self, preset_name: str) -> None:
        preset = _THEME_PRESETS.get(preset_name, _THEME_PRESETS["Corporate Blue"])
        globals().update(preset)

    def _notify(self, title: str, message: str) -> None:
        if not self.settings.get("notifications_enabled", True):
            return
        try:
            messagebox.showinfo(title, message)
        except Exception:
            log_exception("Notification display failed")

    def _track(self, event: str, **details: Any) -> None:
        try:
            if not self.settings.get("telemetry_enabled", True):
                return
            record_usage_event(event, **details)
        except Exception:
            log_exception(f"Usage telemetry failed event={event!r}")

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
            ("search", self._t("Catalog Search"), self._show_search),
            ("library", self._t("Library"), self._show_library),
            ("history", self._t("Download History"), self._show_history),
            ("analytics", self._t("Analytics"), self._show_analytics),
            ("devices", self._t("Devices"), self._show_devices),
            ("settings", self._t("Settings"), self._show_settings),
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
        self.content.pack_propagate(False)

    def _build_shell_refresh(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self.nav_buttons = {}
        self._build_shell()
        self._show_settings()

    def _show_onboarding_if_needed(self) -> None:
        if self.settings.get("onboarding_completed", False):
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("Welcome to AutoBook")
        dialog.geometry("560x360")
        dialog.configure(fg_color=_SURFACE)
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="Welcome to AutoBook", font=ctk.CTkFont(size=24, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=24, pady=(24, 8))
        for line in [
            "1. Search the catalog and download a book.",
            "2. Organize titles with collections and favorites.",
            "3. Use OCR, conversion, device transfer and analytics as needed.",
        ]:
            ctk.CTkLabel(dialog, text=line, font=ctk.CTkFont(size=14), text_color=_TEXT_MUTED, justify="left").pack(anchor="w", padx=24, pady=4)
        ctk.CTkButton(
            dialog,
            text="Start Using AutoBook",
            width=180,
            height=40,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            corner_radius=14,
            text_color=_TEXT,
            command=lambda: (update_settings(onboarding_completed=True), self._refresh_settings_cache(), dialog.destroy()),
        ).pack(anchor="w", padx=24, pady=(18, 0))

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

    def _allowed_formats(self) -> set[str]:
        formats = self.settings.get("allowed_formats", ["EPUB", "PDF"])
        if not isinstance(formats, list):
            return {"EPUB", "PDF"}
        return {str(item).upper() for item in formats}

    def _action_allowed(self, action: str) -> bool:
        allowed = self.settings.get("allowed_actions", ["download", "transfer", "ocr", "convert", "ai"])
        if not isinstance(allowed, list):
            return True
        return action in allowed

    def _active_device_profile(self) -> dict[str, str]:
        active = self.settings.get("active_device_profile", "Default")
        for profile in get_device_profiles():
            if profile.get("name") == active:
                return profile
        return get_device_profiles()[0]

    def _execute_download_job(self, selected_link: Any, book: BookResult) -> tuple[str, str]:
        allowed_formats = self._allowed_formats()
        if selected_link.format.upper() not in allowed_formats:
            raise RuntimeError(f"{selected_link.format.upper()} downloads are disabled by policy.")

        ordered_links = [selected_link] + [link for link in book.downloads if link.url != selected_link.url and link.format == selected_link.format]
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
                self._track("download_success", title=book.title, source=book.source, format=link.format.upper())
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
        self._track("download_failed", title=book.title, source=book.source, format=selected_link.format.upper())
        raise RuntimeError(last_error)

    def _enqueue_download(self, selected_link: Any, book: BookResult) -> None:
        try:
            job = enqueue_download_job(
                {
                    "book": book_result_to_dict(book),
                    "link": {
                        "url": selected_link.url,
                        "format": selected_link.format,
                        "mirror": getattr(selected_link, "mirror", ""),
                    },
                }
            )
            self._track("queue_enqueued", title=book.title, format=selected_link.format.upper())
            self._set_status(f'Queued "{book.title}" for download.')
            if self.settings.get("queue_autostart", True):
                self._start_queue_processing()
        except Exception:
            log_exception("Queue enqueue failed")
            self._set_status("Could not enqueue the download. Check the log for details.")

    def _start_queue_processing(self) -> None:
        if self.queue_processing:
            return
        self.queue_processing = True

        def _runner() -> None:
            try:
                while True:
                    job = get_next_queued_job()
                    if not job:
                        break
                    update_download_job(job["id"], status="running")
                    book = book_result_from_dict(job.get("book", {}))
                    link = download_link_from_dict(job.get("link", {}))
                    try:
                        _filename, message = self._execute_download_job(link, book)
                        update_download_job(job["id"], status="success", message=message)
                        self.after(0, lambda msg=message: self._set_status(msg))
                    except Exception as exc:
                        update_download_job(job["id"], status="failed", message=str(exc))
                        self.after(0, lambda err=str(exc): self._set_status(f"Queued download failed: {err}"))
            finally:
                self.queue_processing = False

        threading.Thread(target=_runner, daemon=True, name="download-queue").start()

    def _clear_queue_finished(self) -> None:
        try:
            removed = clear_finished_queue_jobs()
            self._track("queue_cleared", removed=removed)
            self._set_status(f"Removed {removed} finished queue item(s).")
            if hasattr(self, "_show_history"):
                self._show_history()
        except Exception:
            log_exception("Queue cleanup failed")
            self._set_status("Could not clear finished queue items.")

    def _queue_cancel(self, job_id: str) -> None:
        try:
            cancel_download_job(job_id)
            self._track("queue_cancelled", job_id=job_id)
            self._show_history()
            self._set_status("Queue item cancelled.")
        except Exception:
            log_exception("Queue cancel failed")
            self._set_status("Could not cancel queue item.")

    def _queue_retry(self, job_id: str) -> None:
        try:
            retry_download_job(job_id)
            self._track("queue_retried", job_id=job_id)
            self._show_history()
            self._set_status("Queue item set back to queued.")
        except Exception:
            log_exception("Queue retry failed")
            self._set_status("Could not retry queue item.")

    def _queue_reorder(self, job_id: str, direction: str) -> None:
        try:
            reorder_download_job(job_id, direction)
            self._track("queue_reordered", job_id=job_id, direction=direction)
            self._show_history()
            self._set_status("Queue order updated.")
        except Exception:
            log_exception("Queue reorder failed")
            self._set_status("Could not reorder queue item.")

    def _create_header(self, title: str, subtitle: str, action_text: str | None = None, action_command: Callable[[], None] | None = None) -> None:
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(14, 8))

        text_col = ctk.CTkFrame(header, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(text_col, text=title, font=ctk.CTkFont(size=24, weight="bold"), text_color=_TEXT).pack(anchor="w")
        ctk.CTkLabel(text_col, text=subtitle, font=ctk.CTkFont(size=12), text_color=_TEXT_MUTED).pack(anchor="w", pady=(2, 0))

        if action_text and action_command:
            ctk.CTkButton(
                header,
                text=action_text,
                command=action_command,
                width=102,
                height=34,
                corner_radius=12,
                fg_color=_SURFACE,
                hover_color=_SURFACE_ALT,
                border_width=1,
                border_color=_CARD_BORDER,
                text_color=_TEXT,
            ).pack(side="right")

    def _summary_row(self, items: list[tuple[str, str]]) -> None:
        row = ctk.CTkFrame(self.content, fg_color="transparent")
        row.pack(fill="x", padx=28, pady=(0, 10))
        columns = 2 if len(items) >= 4 else max(1, len(items))
        for col in range(columns):
            row.grid_columnconfigure(col, weight=1)
        for idx, (label, value) in enumerate(items):
            card = ctk.CTkFrame(row, fg_color=_SURFACE, corner_radius=18, border_width=1, border_color=_CARD_BORDER)
            grid_row = idx // columns
            grid_col = idx % columns
            card.grid(row=grid_row, column=grid_col, sticky="nsew", padx=6, pady=6)
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=12, weight="bold"), text_color=_TEXT_SOFT).pack(
                anchor="w", padx=14, pady=(10, 2)
            )
            ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=20, weight="bold"), text_color=_TEXT).pack(
                anchor="w", padx=14, pady=(0, 10)
            )

    def _make_surface(self, parent: Any, pady: tuple[int, int] = (0, 0)) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_SURFACE, corner_radius=18, border_width=1, border_color=_CARD_BORDER)
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

    def _render_stat_bars(self, parent: Any, values: dict[str, int]) -> None:
        if not values:
            ctk.CTkLabel(parent, text="No data yet.", font=ctk.CTkFont(size=13), text_color=_TEXT_MUTED).pack(anchor="w", padx=18, pady=(0, 16))
            return
        top = max(values.values()) if values else 1
        for key, count in values.items():
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=5)
            ctk.CTkLabel(row, text=str(key), font=ctk.CTkFont(size=13), text_color=_TEXT, width=180, anchor="w").pack(side="left")
            bar_wrap = ctk.CTkFrame(row, fg_color="transparent")
            bar_wrap.pack(side="left", fill="x", expand=True, padx=(0, 12))
            ctk.CTkProgressBar(bar_wrap, progress_color=_ACCENT, fg_color=_CARD_BG).pack(fill="x")
            progress = bar_wrap.winfo_children()[0]
            progress.set(0 if top == 0 else count / top)
            ctk.CTkLabel(row, text=str(count), font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT_MUTED, width=48, anchor="e").pack(side="right")

    def _estimated_content_width(self, fallback: int = 1100) -> int:
        width = self.content.winfo_width() if hasattr(self, "content") else 0
        return width if width > 100 else fallback

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
        self._track("view_search")

        self._create_header("Catalog Search", "Find titles and stay in the result stream.")

        panel = self._make_surface(self.content, (0, 8))

        search_row = ctk.CTkFrame(panel, fg_color="transparent")
        search_row.pack(fill="x", padx=18, pady=(14, 10))
        search_row.grid_columnconfigure(0, weight=1)
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
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda _event: self._do_search())
        ctk.CTkButton(
            search_row,
            text=self._t("Search"),
            width=128,
            height=46,
            corner_radius=14,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            text_color=_TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._do_search,
        ).grid(row=0, column=1, sticky="e")

        toolbar_row = ctk.CTkFrame(panel, fg_color="transparent")
        toolbar_row.pack(fill="x", padx=18, pady=(0, 10))
        self.search_filters_visible = tk.BooleanVar(value=False)
        ctk.CTkButton(
            toolbar_row,
            text=self._t("Advanced Filters"),
            width=140,
            height=32,
            corner_radius=12,
            fg_color=_SURFACE_ALT,
            hover_color=_CARD_BG,
            border_width=1,
            border_color=_CARD_BORDER,
            text_color=_TEXT,
            command=self._toggle_search_filters,
        ).pack(side="left")
        ctk.CTkButton(
            toolbar_row,
            text=self._t("AI Suggestions"),
            width=126,
            height=32,
            corner_radius=12,
            fg_color=_SURFACE_ALT,
            hover_color=_CARD_BG,
            border_width=1,
            border_color=_CARD_BORDER,
            text_color=_TEXT,
            command=self._show_ai_search_suggestions,
        ).pack(side="left", padx=(8, 0))
        self.search_context_label = ctk.CTkLabel(
            toolbar_row,
            text="Source: all  |  Format: any  |  Sort: relevance",
            font=ctk.CTkFont(size=11),
            text_color=_TEXT_SOFT,
            anchor="w",
        )
        self.search_context_label.pack(side="left", padx=(12, 0))

        filter_row = ctk.CTkFrame(panel, fg_color="transparent")
        filter_row.pack(fill="x", padx=18, pady=(0, 10))
        for col in range(3):
            filter_row.grid_columnconfigure(col, weight=1)
        self.search_filter_row = filter_row
        self.search_source_var = tk.StringVar(value=self.settings.get("preferred_source", "All Sources"))
        self.search_language_var = tk.StringVar(value="All Languages")
        self.search_format_var = tk.StringVar(value=self.settings.get("preferred_format", "Any"))
        self.search_rating_var = tk.StringVar(value="Any rating")
        self.search_sort_var = tk.StringVar(value="Relevance")

        self._make_filter(filter_row, 0, "Source", self.search_source_var, ["All Sources", "Project Gutenberg", "Open Library", "External"])
        self._make_filter(filter_row, 1, "Language", self.search_language_var, ["All Languages", "English", "Turkish", "Other"])
        self._make_filter(filter_row, 2, "Format", self.search_format_var, ["Any", "EPUB", "PDF"])
        self._make_filter(filter_row, 3, "Min rating", self.search_rating_var, ["Any rating", "3+", "4+"])
        self._make_filter(filter_row, 4, "Sort", self.search_sort_var, ["Relevance", "Rating", "Newest", "Title"])
        self.search_filter_row.pack_forget()
        self._update_search_context_label()

        self.inline_status = ctk.CTkLabel(self.content, text="Ready for search.", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w")
        self.inline_status.pack(fill="x", padx=30, pady=(0, 4))

        self.results_frame = ScrollableFrame(self.content, fg_color=_APP_BG)
        self.results_frame.pack(fill="both", expand=True, padx=28, pady=(0, 12))
        self._render_search_placeholder()
        self.search_entry.focus()

    def _toggle_search_filters(self) -> None:
        if not hasattr(self, "search_filter_row"):
            return
        visible = self.search_filters_visible.get()
        if visible:
            self.search_filter_row.pack_forget()
            self.search_filters_visible.set(False)
        else:
            self.search_filter_row.pack(fill="x", padx=18, pady=(0, 10))
            self.search_filters_visible.set(True)

    def _update_search_context_label(self) -> None:
        if hasattr(self, "search_context_label"):
            self.search_context_label.configure(
                text=(
                    f"Source: {self.search_source_var.get().lower()}  |  "
                    f"Format: {self.search_format_var.get().lower()}  |  "
                    f"Sort: {self.search_sort_var.get().lower()}"
                )
            )

    def _make_filter(self, parent: ctk.CTkFrame, index: int, label: str, var: tk.StringVar, values: list[str]) -> None:
        group = ctk.CTkFrame(parent, fg_color="transparent")
        row = index // 3
        col = index % 3
        group.grid(row=row, column=col, sticky="ew", padx=5, pady=5)
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
            command=lambda _value: (self._update_search_context_label(), self._render_filtered_search_results()),
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

    def _show_ai_search_suggestions(self) -> None:
        if not ai_is_configured():
            self._set_status("OPENAI_API_KEY is not configured for AI search suggestions.")
            return
        query = self.search_entry.get().strip() if hasattr(self, "search_entry") else ""
        if not query:
            self._set_status("Enter a query first to request AI suggestions.")
            return
        suggestions = ai_generate_search_suggestions(query)
        if not suggestions:
            self._set_status("No AI suggestions were generated.")
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("AI Search Suggestions")
        dialog.geometry("520x320")
        dialog.configure(fg_color=_SURFACE)
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="AI Search Suggestions", font=ctk.CTkFont(size=20, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=20, pady=(18, 8))
        for suggestion in suggestions:
            ctk.CTkButton(
                dialog,
                text=suggestion,
                height=38,
                fg_color=_CARD_BG,
                hover_color=_SURFACE_ALT,
                border_width=1,
                border_color=_CARD_BORDER,
                corner_radius=12,
                text_color=_TEXT,
                command=lambda value=suggestion: (self.search_entry.delete(0, "end"), self.search_entry.insert(0, value), dialog.destroy()),
            ).pack(fill="x", padx=20, pady=5)

    def _do_search(self) -> None:
        query = self.search_entry.get().strip()
        if not query:
            self._set_status("Please enter a search query.")
            return
        self._track("search_submitted", query=query[:80])

        for widget in self.results_frame.winfo_children():
            widget.destroy()
        self._set_status(f'Searching sources for "{query}"...')
        self.update_idletasks()

        def _work() -> list[BookResult]:
            log_info(f"Running search for query={query!r}")
            results = search_books(query, allowed_sources=self.settings.get("allowed_sources", []))
            if results and self.settings.get("search_cache_enabled", True):
                save_search_cache(query, [book_result_to_dict(item) for item in results])
            if results:
                return results
            cached = load_search_cache(query, int(self.settings.get("search_cache_max_age_hours", 72) or 72))
            if cached:
                self.after(0, lambda: self._set_status(f'Loaded cached results for "{query}".'))
                return [book_result_from_dict(item) for item in cached if isinstance(item, dict)]
            return []

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
        hero = ctk.CTkFrame(self.results_frame.inner, fg_color=_CARD_BG, corner_radius=16, border_width=1, border_color=_CARD_BORDER)
        hero.pack(fill="x", padx=2, pady=(2, 8))
        ctk.CTkLabel(hero, text=f'{len(results)} results for "{query}"', font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=18, pady=(12, 12))
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
        card.grid_columnconfigure(1, weight=1)

        cover = ctk.CTkLabel(card, text="BOOK", width=104, height=148, fg_color=_CARD_BG, corner_radius=14, text_color=_TEXT_SOFT)
        cover.grid(row=0, column=0, padx=(16, 10), pady=16, sticky="nw")
        if book.cover_url:
            self._load_cover_async(book.cover_url, cover)

        content_width = max(360, self._estimated_content_width() - 520)
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, padx=8, pady=16, sticky="nsew")
        ctk.CTkLabel(info, text=book.title, font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT, anchor="w", justify="left", wraplength=content_width).pack(anchor="w")
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
                wraplength=content_width,
                justify="left",
            ).pack(anchor="w", pady=(10, 0))

        if book.subjects:
            subjects = ctk.CTkFrame(info, fg_color="transparent")
            subjects.pack(anchor="w", pady=(10, 0))
            for subject in book.subjects[:4]:
                self._make_badge(subjects, subject, _SURFACE_ALT)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=0, column=2, padx=16, pady=16, sticky="ne")
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
            ctk.CTkButton(
                actions,
                text=f"Queue {link.format.upper()}",
                width=172,
                height=32,
                fg_color=_SURFACE_ALT,
                hover_color=_CARD_BG,
                border_width=1,
                border_color=_CARD_BORDER,
                corner_radius=12,
                text_color=_TEXT,
                command=lambda dl=link, item=book: self._enqueue_download(dl, item),
            ).pack(pady=(0, 4))
            if link.mirror:
                ctk.CTkLabel(actions, text=link.mirror, font=ctk.CTkFont(size=11), text_color=_TEXT_SOFT).pack(pady=(0, 4))
        if not book.downloads:
            ctk.CTkLabel(actions, text="No direct file available", text_color=_TEXT_SOFT).pack()

    def _download_book(self, selected_link: Any, book: BookResult) -> None:
        self._refresh_settings_cache()
        if not self._action_allowed("download"):
            self._set_status("Downloads are disabled by workspace policy.")
            return
        if book.source and book.source not in self.settings.get("allowed_sources", []):
            self._set_status(f"{book.source} is disabled by source access control.")
            return
        if selected_link.format.upper() not in self._allowed_formats():
            self._set_status(f"{selected_link.format.upper()} downloads are disabled by policy.")
            return
        self._set_status(f'Downloading "{book.title}" as {selected_link.format.upper()}...')
        self.update_idletasks()

        def _work() -> tuple[str, str]:
            return self._execute_download_job(selected_link, book)

        def _done(_result: tuple[str, str]) -> None:
            filename, message = _result
            self._set_status(message)
            self._notify("AutoBook", message)
            profile = self._active_device_profile()
            if profile.get("auto_send"):
                matches = [device for device in detect_devices() if profile.get("kind", "Generic") in {"Generic", device.kind, device.name}]
                if len(matches) == 1:
                    book_entry = next((item for item in get_all_books() if item.get("filename") == filename), None)
                    if book_entry:
                        self._do_transfer(book_entry, matches[0])
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

        controls = self._make_surface(self.content, (0, 8))
        row = ctk.CTkFrame(controls, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(14, 10))
        row.grid_columnconfigure(0, weight=1)
        self.library_search_var = tk.StringVar()
        self.library_collection_var = tk.StringVar(value="All Collections")
        self.library_format_var = tk.StringVar(value="All Formats")
        self.library_source_var = tk.StringVar(value="All Sources")
        self.library_favorites_var = tk.BooleanVar(value=False)
        self.library_status_var = tk.StringVar(value="All Statuses")
        self.library_view_var = tk.StringVar(value=self.settings.get("library_view", "List"))
        self.library_bulk_mode_var = tk.BooleanVar(value=False)
        self.library_advanced_visible = tk.BooleanVar(value=False)

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
        search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        search_entry.bind("<KeyRelease>", lambda _event: self._refresh_library_results())
        ctk.CTkButton(
            row,
            text=self._t("Filters"),
            width=94,
            height=34,
            fg_color=_SURFACE_ALT,
            hover_color=_CARD_BG,
            border_width=1,
            border_color=_CARD_BORDER,
            text_color=_TEXT,
            command=self._toggle_library_advanced,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkOptionMenu(
            row,
            values=["List", "Grid"],
            variable=self.library_view_var,
            width=100,
            height=34,
            fg_color=_CARD_BG,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_SURFACE_ALT,
            text_color=_TEXT,
            dropdown_text_color=_TEXT,
            command=lambda _value: self._refresh_library_results(),
        ).grid(row=0, column=2)

        filter_frame = ctk.CTkFrame(controls, fg_color="transparent")
        filter_frame.pack(fill="x", padx=18, pady=(0, 10))
        for col in range(3):
            filter_frame.grid_columnconfigure(col, weight=1)
        self.library_filter_frame = filter_frame
        self._make_library_filter(filter_frame, 0, "Collection", self.library_collection_var, ["All Collections", *list_collections()])
        self._make_library_filter(filter_frame, 1, "Format", self.library_format_var, ["All Formats", "EPUB", "PDF"])
        sources = sorted({book.get("source", "") for book in books if book.get("source")})
        self._make_library_filter(filter_frame, 2, "Source", self.library_source_var, ["All Sources", *sources])
        self._make_library_filter(filter_frame, 3, "Status", self.library_status_var, ["All Statuses", "Unread", "Reading", "Completed"])
        ctk.CTkCheckBox(
            filter_frame,
            text=self._t("Favorites only"),
            variable=self.library_favorites_var,
            command=self._refresh_library_results,
            text_color=_TEXT,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            border_color=_CARD_BORDER,
        ).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(28, 0))
        ctk.CTkCheckBox(
            filter_frame,
            text=self._t("Bulk mode"),
            variable=self.library_bulk_mode_var,
            command=self._refresh_library_results,
            text_color=_TEXT,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            border_color=_CARD_BORDER,
        ).grid(row=2, column=0, sticky="w", padx=(8, 0), pady=(8, 0))
        self.library_filter_frame.pack_forget()

        bulk_row = ctk.CTkFrame(controls, fg_color="transparent")
        bulk_row.pack(fill="x", padx=18, pady=(0, 10))
        self.library_bulk_row = bulk_row
        self.bulk_status_label = ctk.CTkLabel(bulk_row, text="0 selected", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT)
        self.bulk_status_label.pack(side="left", padx=(0, 14))
        ctk.CTkButton(bulk_row, text=self._t("Favorite Selected"), width=138, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=self._bulk_mark_favorite).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bulk_row, text=self._t("Set Reading"), width=118, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=self._bulk_set_reading).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bulk_row, text=self._t("Add Collection"), width=122, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=self._bulk_add_collection).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bulk_row, text=self._t("Batch OCR"), width=106, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=self._bulk_run_ocr).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bulk_row, text=self._t("Batch Convert"), width=118, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=self._bulk_convert_books).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bulk_row, text=self._t("Remove Selected"), width=132, height=34, fg_color=_DANGER, hover_color=_DANGER_HOVER, text_color=_TEXT, command=self._bulk_remove_books).pack(side="left")
        self.library_bulk_row.pack_forget()

        recommendations = get_recommendations(limit=4)
        if recommendations:
            rec_panel = ctk.CTkFrame(controls, fg_color=_CARD_BG, corner_radius=16, border_width=1, border_color=_CARD_BORDER)
            rec_panel.pack(fill="x", padx=18, pady=(0, 10))
            self.library_recommendations_panel = rec_panel
            ctk.CTkLabel(rec_panel, text="Recommended from your library", font=ctk.CTkFont(size=14, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=16, pady=(12, 4))
            rec_row = ctk.CTkFrame(rec_panel, fg_color="transparent")
            rec_row.pack(fill="x", padx=16, pady=(0, 14))
            for book in recommendations:
                self._make_badge(rec_row, book.get("title", "Unknown")[:24], _SURFACE_ALT)
            self.library_recommendations_panel.pack_forget()
        else:
            self.library_recommendations_panel = None

        self.inline_status = ctk.CTkLabel(self.content, text="", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w")
        self.inline_status.pack(fill="x", padx=30, pady=(0, 4))
        self.library_results = ScrollableFrame(self.content, fg_color=_APP_BG)
        self.library_results.pack(fill="both", expand=True, padx=28, pady=(0, 12))
        self._refresh_library_results()

    def _toggle_library_advanced(self) -> None:
        if not hasattr(self, "library_filter_frame"):
            return
        visible = self.library_advanced_visible.get()
        if visible:
            self.library_filter_frame.pack_forget()
            self.library_advanced_visible.set(False)
        else:
            self.library_filter_frame.pack(fill="x", padx=18, pady=(0, 10))
            self.library_advanced_visible.set(True)

    def _make_library_filter(self, parent: ctk.CTkFrame, index: int, label: str, var: tk.StringVar, values: list[str]) -> None:
        group = ctk.CTkFrame(parent, fg_color="transparent")
        row = index // 3
        col = index % 3
        group.grid(row=row, column=col, sticky="ew", padx=5, pady=5)
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
        if hasattr(self, "library_bulk_row"):
            if self.library_bulk_mode_var.get():
                self.library_bulk_row.pack(fill="x", padx=18, pady=(0, 10))
            else:
                self.library_bulk_row.pack_forget()
        if getattr(self, "library_recommendations_panel", None) is not None:
            if not books and self.library_recommendations_panel is not None:
                self.library_recommendations_panel.pack(fill="x", padx=18, pady=(0, 10))
            else:
                self.library_recommendations_panel.pack_forget()
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
            ctk.CTkLabel(card, text=book.get("summary", "")[:120], font=ctk.CTkFont(size=11), text_color=_TEXT_SOFT, wraplength=260, justify="left").pack(anchor="w", padx=16, pady=(8, 10))
            badges = ctk.CTkFrame(card, fg_color="transparent")
            badges.pack(anchor="w", padx=16, pady=(0, 10))
            for text, color in [
                (book.get("format", "").upper(), _ACCENT_SOFT),
                (book.get("reading_status", ""), _SURFACE_ALT),
            ]:
                if text:
                    self._make_badge(badges, text, color)
            for category in book.get("auto_categories", [])[:2]:
                self._make_badge(badges, category, _CARD_BG)
            ctk.CTkButton(card, text="Edit", width=90, height=32, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=lambda b=book: self._edit_book_details(b["id"])).pack(anchor="w", padx=16, pady=(0, 16))

    def _make_library_card(self, book: dict[str, Any]) -> None:
        card = ctk.CTkFrame(self.library_results.inner, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
        card.pack(fill="x", pady=6, padx=2)
        card.grid_columnconfigure(1, weight=1)
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
        cover.grid(row=0, column=0, padx=(40 if self.library_bulk_mode_var.get() else 16, 10), pady=16, sticky="nw")
        if book.get("cover_url"):
            self._load_cover_async(book["cover_url"], cover, (82, 118))

        content_width = max(340, self._estimated_content_width() - 520)
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, padx=8, pady=16, sticky="nsew")
        title_row = ctk.CTkFrame(info, fg_color="transparent")
        title_row.pack(fill="x")
        ctk.CTkLabel(title_row, text=book.get("title", "Unknown"), font=ctk.CTkFont(size=17, weight="bold"), text_color=_TEXT, anchor="w", wraplength=content_width).pack(side="left", anchor="w")
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
        if book.get("summary"):
            ctk.CTkLabel(info, text=book["summary"][:180], font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, wraplength=content_width, justify="left").pack(anchor="w", pady=(0, 8))

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
        for category in book.get("auto_categories", [])[:2]:
            self._make_badge(badges, category, _ACCENT_SOFT)

        if book.get("notes"):
            ctk.CTkLabel(info, text=f'Notes: {book.get("notes", "")[:90]}', font=ctk.CTkFont(size=11), text_color=_TEXT_SOFT, wraplength=content_width, justify="left").pack(anchor="w", pady=(10, 0))
        ctk.CTkLabel(info, text=book.get("filename", ""), font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w").pack(anchor="w", pady=(6, 0))

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=0, column=2, padx=16, pady=16, sticky="ne")
        for text, cmd, fg, hover in [
            (self._t("Edit"), lambda b=book: self._edit_book_details(b["id"]), _SURFACE_ALT, _CARD_BG),
            (self._t("Open File"), lambda b=book: self._open_book_file(b), _ACCENT, _ACCENT_HOVER),
            ("Collections", lambda b=book: self._edit_collections(b["id"]), _SURFACE_ALT, _CARD_BG),
            (self._t("Send to Device"), lambda b=book: self._send_to_device(b), _SURFACE_ALT, _CARD_BG),
            (self._t("Repair"), lambda b=book: self._repair_book(b["id"]), _SURFACE_ALT, _CARD_BG),
            (self._t("Run OCR"), lambda b=book: self._run_book_ocr(b["id"]), _SURFACE_ALT, _CARD_BG),
            (self._t("Convert"), lambda b=book: self._convert_book(b["id"]), _SURFACE_ALT, _CARD_BG),
            (self._t("AI Enrich"), lambda b=book: self._ai_enrich_book(b["id"]), _SURFACE_ALT, _CARD_BG),
            ("AI Tags", lambda b=book: self._ai_generate_tags_for_book(b["id"]), _SURFACE_ALT, _CARD_BG),
            (self._t("Remove"), lambda b=book: self._delete_book(b), _DANGER, _DANGER_HOVER),
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

    def _bulk_run_ocr(self) -> None:
        if not self.selected_book_ids:
            self._set_status("Select at least one book in bulk mode.")
            return
        self._set_status("Running batch OCR...")

        def _work() -> dict[str, Any]:
            return run_ocr_for_books(list(self.selected_book_ids))

        def _done(result: dict[str, Any]) -> None:
            self._track("bulk_ocr", completed=result.get("completed", 0))
            self._set_status(f'Batch OCR finished. {result.get("completed", 0)} completed, {len(result.get("failures", []))} failed.')
            self._refresh_library_results()

        self._run_background(_work, _done, user_error="Batch OCR failed.")

    def _bulk_convert_books(self) -> None:
        if not self.selected_book_ids:
            self._set_status("Select at least one book in bulk mode.")
            return
        dialog = ctk.CTkInputDialog(text="Target format for selected books: epub, pdf, or txt", title="Batch Convert")
        target = (dialog.get_input() or "").strip().lower()
        if not target:
            return
        self._set_status(f"Running batch conversion to {target.upper()}...")

        def _work() -> dict[str, Any]:
            return convert_books(list(self.selected_book_ids), target)

        def _done(result: dict[str, Any]) -> None:
            self._track("bulk_convert", completed=result.get("completed", 0), format=target.upper())
            self._set_status(f'Batch conversion finished. {result.get("completed", 0)} completed, {len(result.get("failures", []))} failed.')

        self._run_background(_work, _done, user_error="Batch conversion failed.")

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

    def _repair_book(self, book_id: str) -> None:
        try:
            result = repair_book_file(book_id)
            self._track("book_repaired", book_id=book_id, status=result.get("status", "unknown"))
            self._set_status(result.get("message", "Repair finished."))
            self._notify("AutoBook", result.get("message", "Repair finished."))
        except Exception as exc:
            log_exception("Book repair failed")
            self._set_status(f"Repair failed: {exc}")

    def _run_book_ocr(self, book_id: str) -> None:
        if not self._action_allowed("ocr"):
            self._set_status("OCR is disabled by workspace policy.")
            return
        self._set_status("Running OCR...")
        self.update_idletasks()

        def _work() -> dict[str, Any]:
            return run_ocr_for_book(book_id)

        def _done(result: dict[str, Any]) -> None:
            self._track("book_ocr", book_id=book_id, chars=result.get("chars", 0))
            self._set_status(f"OCR completed. Output: {result.get('output', '')}")
            self._notify("AutoBook", "OCR completed.")
            self._refresh_library_results()

        self._run_background(_work, _done, user_error="OCR failed.")

    def _convert_book(self, book_id: str) -> None:
        if not self._action_allowed("convert"):
            self._set_status("Conversion is disabled by workspace policy.")
            return
        dialog = ctk.CTkInputDialog(text="Target format: epub, pdf, or txt", title="Convert Book")
        target = (dialog.get_input() or "").strip().lower()
        if not target:
            return
        self._set_status(f"Converting book to {target.upper()}...")
        self.update_idletasks()

        def _work() -> dict[str, Any]:
            return convert_book_format(book_id, target)

        def _done(result: dict[str, Any]) -> None:
            self._track("book_converted", book_id=book_id, format=result.get("format", target.upper()))
            self._set_status(f"Conversion completed: {result.get('output', '')}")
            self._notify("AutoBook", f"Conversion completed to {result.get('format', target.upper())}.")

        self._run_background(_work, _done, user_error="Conversion failed.")

    def _ai_enrich_book(self, book_id: str) -> None:
        if not self._action_allowed("ai"):
            self._set_status("AI actions are disabled by workspace policy.")
            return
        if not ai_is_configured():
            self._set_status("OPENAI_API_KEY is not configured for AI enrichment.")
            return
        self._set_status("Generating AI enrichment...")
        self.update_idletasks()

        def _work() -> dict[str, Any]:
            return ai_enrich_book(book_id)

        def _done(result: dict[str, Any]) -> None:
            self._track("ai_enrichment", book_id=book_id)
            self._set_status(f"AI enrichment updated {len(result.get('categories', []))} categories.")
            self._refresh_library_results()

        self._run_background(_work, _done, user_error="AI enrichment failed.")

    def _ai_generate_tags_for_book(self, book_id: str) -> None:
        if not self._action_allowed("ai"):
            self._set_status("AI actions are disabled by workspace policy.")
            return
        if not ai_is_configured():
            self._set_status("OPENAI_API_KEY is not configured for AI tag generation.")
            return

        def _work() -> dict[str, Any]:
            return ai_generate_tags(book_id)

        def _done(result: dict[str, Any]) -> None:
            self._track("ai_tags", book_id=book_id)
            self._set_status(f'AI tags updated: {", ".join(result.get("tags", []))}')
            self._refresh_library_results()

        self._run_background(_work, _done, user_error="AI tag generation failed.")

    # History page

    def _show_history(self) -> None:
        self._set_active_nav("history")
        self._clear_content()
        self._track("view_history")
        history = get_download_history()
        self._create_header("Download History", "Review successful and failed download attempts with timestamps and messages.", "Refresh", self._show_history)
        self._summary_row(self._history_summary_items(history))
        self.inline_status = ctk.CTkLabel(self.content, text=f"{len(history)} history event(s).", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w")
        self.inline_status.pack(fill="x", padx=30, pady=(0, 4))

        queue_items = get_download_queue()
        queue_panel = self._make_surface(self.content, (0, 8))
        queue_row = ctk.CTkFrame(queue_panel, fg_color="transparent")
        queue_row.pack(fill="x", padx=18, pady=(14, 12))
        ctk.CTkLabel(queue_row, text=self._t("Download queue"), font=ctk.CTkFont(size=16, weight="bold"), text_color=_TEXT).pack(side="left")
        ctk.CTkButton(queue_row, text=self._t("Run Queue"), width=110, height=32, fg_color=_ACCENT, hover_color=_ACCENT_HOVER, corner_radius=12, text_color=_TEXT, command=self._start_queue_processing).pack(side="right", padx=(8, 0))
        ctk.CTkButton(queue_row, text=self._t("Clear Finished"), width=120, height=32, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, corner_radius=12, border_width=1, border_color=_CARD_BORDER, text_color=_TEXT, command=self._clear_queue_finished).pack(side="right")
        if queue_items:
            for item in queue_items[:6]:
                row = ctk.CTkFrame(queue_panel, fg_color="transparent")
                row.pack(fill="x", padx=18, pady=4)
                title = item.get("book", {}).get("title", "Queued title") if isinstance(item.get("book"), dict) else "Queued title"
                left = ctk.CTkFrame(row, fg_color="transparent")
                left.pack(side="left", fill="x", expand=True)
                ctk.CTkLabel(left, text=f"{title}  |  {item.get('link', {}).get('format', '').upper()}", font=ctk.CTkFont(size=12), text_color=_TEXT).pack(anchor="w")
                progress = ctk.CTkProgressBar(left, progress_color=_ACCENT, fg_color=_CARD_BG)
                progress.pack(fill="x", pady=(6, 0), padx=(0, 14))
                progress.set({"queued": 0.2, "running": 0.65, "success": 1.0, "failed": 1.0, "cancelled": 1.0}.get(item.get("status", "queued"), 0.2))
                controls = ctk.CTkFrame(row, fg_color="transparent")
                controls.pack(side="right")
                ctk.CTkButton(controls, text="Up", width=42, height=28, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, corner_radius=10, text_color=_TEXT, command=lambda job_id=item.get("id", ""): self._queue_reorder(job_id, "up")).pack(side="left", padx=(6, 0))
                ctk.CTkButton(controls, text="Down", width=54, height=28, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, corner_radius=10, text_color=_TEXT, command=lambda job_id=item.get("id", ""): self._queue_reorder(job_id, "down")).pack(side="left", padx=(6, 0))
                ctk.CTkButton(controls, text="Retry", width=54, height=28, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, corner_radius=10, text_color=_TEXT, command=lambda job_id=item.get("id", ""): self._queue_retry(job_id)).pack(side="left", padx=(6, 0))
                ctk.CTkButton(controls, text="Cancel", width=62, height=28, fg_color=_DANGER if item.get("status") == "queued" else _SURFACE_ALT, hover_color=_DANGER_HOVER if item.get("status") == "queued" else _CARD_BG, corner_radius=10, text_color=_TEXT, command=lambda job_id=item.get("id", ""): self._queue_cancel(job_id)).pack(side="left", padx=(6, 0))
                self._make_badge(row, item.get("status", "queued").upper(), _SURFACE_ALT if item.get("status") == "queued" else (_SUCCESS if item.get("status") == "success" else _DANGER))
        else:
            ctk.CTkLabel(queue_panel, text="No queued downloads.", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT).pack(anchor="w", padx=18, pady=(0, 14))

        if not history:
            self._show_empty_state("No download history yet", "Every download success or failure will appear here so you can quickly inspect what happened.")
            return

        scroll = ScrollableFrame(self.content, fg_color=_APP_BG)
        scroll.pack(fill="both", expand=True, padx=28, pady=(0, 12))
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

    def _show_analytics(self) -> None:
        self._set_active_nav("analytics")
        self._clear_content()
        self._track("view_analytics")
        analytics = get_library_analytics()
        self._create_header("Analytics", "Inspect format, source, language and reading-state distribution across the local library.")
        self._summary_row(
            [
                ("Books", str(analytics.get("total_books", 0))),
                ("Favorites", str(analytics.get("favorites", 0))),
                ("Collections", str(analytics.get("collections", 0))),
                (self._t("Usage telemetry"), str(analytics.get("usage_events", 0))),
            ]
        )
        self.inline_status = ctk.CTkLabel(self.content, text="Analytics are calculated from the local library metadata.", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w")
        self.inline_status.pack(fill="x", padx=30, pady=(0, 4))

        scroll = ScrollableFrame(self.content, fg_color=_APP_BG)
        scroll.pack(fill="both", expand=True, padx=28, pady=(0, 12))
        sections = [
            ("By Source", analytics.get("by_source", {})),
            ("By Format", analytics.get("by_format", {})),
            ("By Reading Status", analytics.get("by_status", {})),
            ("By Language", analytics.get("by_language", {})),
            (self._t("Auto categories"), analytics.get("by_category", {})),
            (self._t("Usage telemetry"), analytics.get("usage_by_event", {})),
        ]
        for title, values in sections:
            card = ctk.CTkFrame(scroll.inner, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
            card.pack(fill="x", padx=2, pady=6)
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=18, pady=(16, 12))
            self._render_stat_bars(card, values)

        trending = analytics.get("trending_titles", [])
        if trending:
            card = ctk.CTkFrame(scroll.inner, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
            card.pack(fill="x", padx=2, pady=6)
            ctk.CTkLabel(card, text=self._t("Trending titles"), font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=18, pady=(16, 10))
            for item in trending:
                row = ctk.CTkFrame(card, fg_color="transparent")
                row.pack(fill="x", padx=18, pady=4)
                text = item.get("title", "Unknown")
                if item.get("author"):
                    text = f"{text} - {item['author']}"
                ctk.CTkLabel(row, text=text, font=ctk.CTkFont(size=13), text_color=_TEXT).pack(side="left")
                ctk.CTkLabel(row, text=f"{item.get('count', 0)} download(s)", font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT_MUTED).pack(side="right")

        usage_events = get_usage_events(limit=8)
        if usage_events:
            card = ctk.CTkFrame(scroll.inner, corner_radius=20, fg_color=_SURFACE, border_width=1, border_color=_CARD_BORDER)
            card.pack(fill="x", padx=2, pady=6)
            ctk.CTkLabel(card, text=self._t("Recent usage events"), font=ctk.CTkFont(size=18, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=18, pady=(16, 10))
            for event in usage_events:
                row = ctk.CTkFrame(card, fg_color="transparent")
                row.pack(fill="x", padx=18, pady=4)
                ctk.CTkLabel(row, text=event.get("event", "unknown"), font=ctk.CTkFont(size=13), text_color=_TEXT).pack(side="left")
                ctk.CTkLabel(row, text=event.get("timestamp", ""), font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT).pack(side="right")

    # Devices page

    def _show_devices(self) -> None:
        self._set_active_nav("devices")
        self._clear_content()
        self._track("view_devices")
        devices = detect_devices()
        transfers = get_transfer_history(limit=6)
        self._create_header("Devices", "Review connected reading devices, install MTP support and run connection diagnostics.", "Scan", self._show_devices)
        self._summary_row(self._device_summary_items(devices))
        active_profile = self._active_device_profile()
        self.inline_status = ctk.CTkLabel(self.content, text=f'Connection scan complete. Active transfer profile: {active_profile.get("name", "Default")}', font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w")
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
        if not self._action_allowed("transfer"):
            self._set_status("Transfers are disabled by workspace policy.")
            return
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
        profile = self._active_device_profile()
        subdir = profile.get("subdir", "").strip() or self.settings.get("device_subdir", "").strip()
        try:
            result = copy_to_device(str(path), device, subdir=subdir)
            record_transfer_history(title=book.get("title", "Unknown"), device_name=device.name, status="success", message=result)
            self._track("transfer_success", title=book.get("title", "Unknown"), device=device.name)
            log_info(f'Transfer completed book={book.get("title", "")!r} device={device.name!r}')
            self._set_status(f'Transfer completed to {device.name}. {result}')
            self._notify("AutoBook", f'Transfer completed to {device.name}.')
        except Exception as exc:
            record_transfer_history(title=book.get("title", "Unknown"), device_name=device.name, status="failed", message=str(exc))
            self._track("transfer_failed", title=book.get("title", "Unknown"), device=device.name)
            log_exception("Device transfer failed")
            self._set_status(f"Transfer failed: {exc}")

    # Settings page

    def _show_settings(self) -> None:
        self._set_active_nav("settings")
        self._clear_content()
        self._refresh_settings_cache()
        self._track("view_settings")
        self._create_header("Settings", "Configure preferred formats, source defaults, transfer behavior and logging access.")
        self._summary_row(
            [
                ("Preferred Format", self.settings.get("preferred_format", "Any")),
                ("Preferred Source", self.settings.get("preferred_source", "All Sources")),
                ("Log File", LOG_FILE.name),
            ]
        )

        panel = self._make_surface(self.content, (0, 10))
        self.settings_format_var = tk.StringVar(value=self.settings.get("preferred_format", "Any"))
        self.settings_source_var = tk.StringVar(value=self.settings.get("preferred_source", "All Sources"))
        self.settings_collection_var = tk.StringVar(value=self.settings.get("default_collection", ""))
        self.settings_device_subdir_var = tk.StringVar(value=self.settings.get("device_subdir", ""))
        self.settings_open_library_var = tk.BooleanVar(value=bool(self.settings.get("open_library_after_download", True)))
        self.settings_organize_var = tk.StringVar(value=self.settings.get("auto_organize_by", "None"))
        self.settings_theme_var = tk.StringVar(value=self.settings.get("theme_preset", "Corporate Blue"))
        self.settings_notifications_var = tk.BooleanVar(value=bool(self.settings.get("notifications_enabled", True)))
        self.settings_telemetry_var = tk.BooleanVar(value=bool(self.settings.get("telemetry_enabled", True)))
        self.settings_language_var = tk.StringVar(value=self.settings.get("interface_language", "English"))
        self.settings_cache_var = tk.BooleanVar(value=bool(self.settings.get("search_cache_enabled", True)))
        self.settings_queue_autostart_var = tk.BooleanVar(value=bool(self.settings.get("queue_autostart", True)))
        self.settings_cache_age_var = tk.StringVar(value=str(self.settings.get("search_cache_max_age_hours", 72)))
        self.settings_role_var = tk.StringVar(value=self.settings.get("workspace_role", "Admin"))
        allowed_actions = set(self.settings.get("allowed_actions", ["download", "transfer", "ocr", "convert", "ai"]))
        self.action_download_var = tk.BooleanVar(value="download" in allowed_actions)
        self.action_transfer_var = tk.BooleanVar(value="transfer" in allowed_actions)
        self.action_ocr_var = tk.BooleanVar(value="ocr" in allowed_actions)
        self.action_convert_var = tk.BooleanVar(value="convert" in allowed_actions)
        self.action_ai_var = tk.BooleanVar(value="ai" in allowed_actions)
        active_formats = set(self.settings.get("allowed_formats", ["EPUB", "PDF"]))
        self.allow_epub_var = tk.BooleanVar(value="EPUB" in active_formats)
        self.allow_pdf_var = tk.BooleanVar(value="PDF" in active_formats)
        profiles = get_device_profiles()
        self.settings_profile_var = tk.StringVar(value=self.settings.get("active_device_profile", profiles[0]["name"]))
        allowed_sources = set(self.settings.get("allowed_sources", ["Project Gutenberg", "Open Library", "External"]))
        self.allow_gutenberg_var = tk.BooleanVar(value="Project Gutenberg" in allowed_sources)
        self.allow_openlibrary_var = tk.BooleanVar(value="Open Library" in allowed_sources)
        self.allow_external_var = tk.BooleanVar(value="External" in allowed_sources)

        form = ctk.CTkFrame(panel, fg_color="transparent")
        form.pack(fill="x", padx=18, pady=16)
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        self._make_settings_field(form, 0, 0, "Preferred download format", ctk.CTkOptionMenu(
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
        self._make_settings_field(form, 0, 1, "Preferred source", ctk.CTkOptionMenu(
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
        self._make_settings_field(form, 1, 0, "Default collection after download", ctk.CTkEntry(
            form,
            textvariable=self.settings_collection_var,
            fg_color=_CARD_BG,
            border_color=_CARD_BORDER,
            text_color=_TEXT,
        ))
        self._make_settings_field(form, 1, 1, "Device subfolder", ctk.CTkEntry(
            form,
            textvariable=self.settings_device_subdir_var,
            fg_color=_CARD_BG,
            border_color=_CARD_BORDER,
            text_color=_TEXT,
        ))
        self._make_settings_field(form, 2, 0, "Auto organize books by", ctk.CTkOptionMenu(
            form,
            values=["None", "Author", "Format", "Source"],
            variable=self.settings_organize_var,
            fg_color=_CARD_BG,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_SURFACE_ALT,
            text_color=_TEXT,
            dropdown_text_color=_TEXT,
        ))
        self._make_settings_field(form, 2, 1, "Theme preset", ctk.CTkOptionMenu(
            form,
            values=list(_THEME_PRESETS.keys()),
            variable=self.settings_theme_var,
            fg_color=_CARD_BG,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_SURFACE_ALT,
            text_color=_TEXT,
            dropdown_text_color=_TEXT,
        ))
        self._make_settings_field(form, 3, 0, self._t("Interface language"), ctk.CTkOptionMenu(
            form,
            values=["English", "Turkish"],
            variable=self.settings_language_var,
            fg_color=_CARD_BG,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_SURFACE_ALT,
            text_color=_TEXT,
            dropdown_text_color=_TEXT,
        ))
        self._make_settings_field(form, 3, 1, "Cache max age (hours)", ctk.CTkEntry(
            form,
            textvariable=self.settings_cache_age_var,
            fg_color=_CARD_BG,
            border_color=_CARD_BORDER,
            text_color=_TEXT,
        ))
        self._make_settings_field(form, 4, 0, "Workspace role", ctk.CTkOptionMenu(
            form,
            values=["Admin", "Operator", "Viewer"],
            variable=self.settings_role_var,
            fg_color=_CARD_BG,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_SURFACE_ALT,
            text_color=_TEXT,
            dropdown_text_color=_TEXT,
        ))

        toggles = ctk.CTkFrame(panel, fg_color="transparent")
        toggles.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkCheckBox(
            toggles,
            text="Open Library after a successful download",
            variable=self.settings_open_library_var,
            text_color=_TEXT,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            border_color=_CARD_BORDER,
        ).pack(anchor="w", pady=(0, 10))
        ctk.CTkCheckBox(
            toggles,
            text="Enable notifications",
            variable=self.settings_notifications_var,
            text_color=_TEXT,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            border_color=_CARD_BORDER,
        ).pack(anchor="w")
        ctk.CTkCheckBox(
            toggles,
            text=self._t("Enable local usage telemetry"),
            variable=self.settings_telemetry_var,
            text_color=_TEXT,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            border_color=_CARD_BORDER,
        ).pack(anchor="w", pady=(10, 0))
        ctk.CTkCheckBox(
            toggles,
            text="Enable offline search cache",
            variable=self.settings_cache_var,
            text_color=_TEXT,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            border_color=_CARD_BORDER,
        ).pack(anchor="w", pady=(10, 0))
        ctk.CTkCheckBox(
            toggles,
            text="Auto-start download queue",
            variable=self.settings_queue_autostart_var,
            text_color=_TEXT,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            border_color=_CARD_BORDER,
        ).pack(anchor="w", pady=(10, 0))

        source_panel = ctk.CTkFrame(panel, fg_color=_CARD_BG, corner_radius=14, border_width=1, border_color=_CARD_BORDER)
        source_panel.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(source_panel, text=self._t("Allowed sources"), font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=14, pady=(12, 8))
        source_row = ctk.CTkFrame(source_panel, fg_color="transparent")
        source_row.pack(fill="x", padx=14, pady=(0, 12))
        for text, var in [
            ("Project Gutenberg", self.allow_gutenberg_var),
            ("Open Library", self.allow_openlibrary_var),
            ("External", self.allow_external_var),
        ]:
            ctk.CTkCheckBox(
                source_row,
                text=text,
                variable=var,
                text_color=_TEXT,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOVER,
                border_color=_CARD_BORDER,
            ).pack(side="left", padx=(0, 14))

        format_panel = ctk.CTkFrame(panel, fg_color=_CARD_BG, corner_radius=14, border_width=1, border_color=_CARD_BORDER)
        format_panel.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(format_panel, text=self._t("Allowed formats"), font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=14, pady=(12, 8))
        format_row = ctk.CTkFrame(format_panel, fg_color="transparent")
        format_row.pack(fill="x", padx=14, pady=(0, 12))
        for text, var in [("EPUB", self.allow_epub_var), ("PDF", self.allow_pdf_var)]:
            ctk.CTkCheckBox(
                format_row,
                text=text,
                variable=var,
                text_color=_TEXT,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOVER,
                border_color=_CARD_BORDER,
            ).pack(side="left", padx=(0, 14))

        policy_panel = ctk.CTkFrame(panel, fg_color=_CARD_BG, corner_radius=14, border_width=1, border_color=_CARD_BORDER)
        policy_panel.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(policy_panel, text=self._t("Allowed actions"), font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=14, pady=(12, 8))
        policy_row = ctk.CTkFrame(policy_panel, fg_color="transparent")
        policy_row.pack(fill="x", padx=14, pady=(0, 12))
        for text, var in [
            ("Download", self.action_download_var),
            ("Transfer", self.action_transfer_var),
            ("OCR", self.action_ocr_var),
            ("Convert", self.action_convert_var),
            ("AI", self.action_ai_var),
        ]:
            ctk.CTkCheckBox(
                policy_row,
                text=text,
                variable=var,
                text_color=_TEXT,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOVER,
                border_color=_CARD_BORDER,
            ).pack(side="left", padx=(0, 14))

        profile_panel = ctk.CTkFrame(panel, fg_color=_CARD_BG, corner_radius=14, border_width=1, border_color=_CARD_BORDER)
        profile_panel.pack(fill="x", padx=18, pady=(0, 12))
        top = ctk.CTkFrame(profile_panel, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 8))
        ctk.CTkLabel(top, text=self._t("Device profiles"), font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT).pack(side="left")
        ctk.CTkOptionMenu(
            top,
            values=[profile["name"] for profile in profiles],
            variable=self.settings_profile_var,
            width=180,
            fg_color=_SURFACE_ALT,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_SURFACE_ALT,
            text_color=_TEXT,
            dropdown_text_color=_TEXT,
        ).pack(side="right")
        active_profile = self._active_device_profile()
        ctk.CTkLabel(profile_panel, text=f"Active profile subfolder: {active_profile.get('subdir', '-') or '-'}  |  Kind: {active_profile.get('kind', 'Generic')}  |  Format: {active_profile.get('preferred_format', 'Any')}  |  Auto-send: {'On' if active_profile.get('auto_send') else 'Off'}", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT).pack(anchor="w", padx=14, pady=(0, 10))
        action_profile = ctk.CTkFrame(profile_panel, fg_color="transparent")
        action_profile.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(action_profile, text=self._t("Add Profile"), width=112, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, corner_radius=12, text_color=_TEXT, command=self._add_device_profile).pack(side="left")
        ctk.CTkButton(action_profile, text=self._t("Delete Profile"), width=120, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, corner_radius=12, text_color=_TEXT, command=self._delete_device_profile_action).pack(side="left", padx=(10, 0))

        diagnostics_panel = ctk.CTkFrame(panel, fg_color=_CARD_BG, corner_radius=14, border_width=1, border_color=_CARD_BORDER)
        diagnostics_panel.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(diagnostics_panel, text="Tooling and extensions", font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=14, pady=(12, 8))
        tooling = get_optional_tooling()
        cache_stats = get_search_cache_stats()
        plugins = list_local_plugins()
        ctk.CTkLabel(diagnostics_panel, text=f"Tesseract: {'Ready' if tooling['tesseract'] else 'Missing'}  |  Pandoc: {'Ready' if tooling['pandoc'] else 'Missing'}  |  ebook-convert: {'Ready' if tooling['ebook-convert'] else 'Missing'}", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT).pack(anchor="w", padx=14, pady=(0, 8))
        ctk.CTkLabel(diagnostics_panel, text=f"AI provider: {'Configured' if ai_is_configured() else 'Missing OPENAI_API_KEY'}", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT).pack(anchor="w", padx=14, pady=(0, 8))
        ctk.CTkLabel(diagnostics_panel, text=f"Offline cache: {cache_stats['entries']} entries  |  {cache_stats['bytes']} bytes", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT).pack(anchor="w", padx=14, pady=(0, 8))
        ctk.CTkLabel(diagnostics_panel, text=f"Local plugins: {len(plugins)}", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT).pack(anchor="w", padx=14, pady=(0, 8))
        for plugin in plugins[:6]:
            row = ctk.CTkFrame(diagnostics_panel, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=2)
            status_text = "enabled" if plugin.get("enabled") == "true" else "disabled"
            ctk.CTkLabel(row, text=f"{plugin['name']} {plugin['version']}  |  {status_text}  |  {plugin['description']}", font=ctk.CTkFont(size=12), text_color=_TEXT_MUTED).pack(side="left")
            ctk.CTkButton(row, text="Toggle", width=72, height=28, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, corner_radius=10, text_color=_TEXT, command=lambda plugin_path=plugin["path"]: self._toggle_plugin(plugin_path)).pack(side="right")
        diag_actions = ctk.CTkFrame(diagnostics_panel, fg_color="transparent")
        diag_actions.pack(fill="x", padx=14, pady=(8, 12))
        ctk.CTkButton(diag_actions, text=self._t("Clear Cache"), width=110, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, corner_radius=12, text_color=_TEXT, command=self._clear_offline_cache).pack(side="left")
        ctk.CTkButton(diag_actions, text=self._t("Web Preview"), width=118, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, corner_radius=12, text_color=_TEXT, command=self._generate_web_preview).pack(side="left", padx=(10, 0))
        ctk.CTkButton(diag_actions, text=self._t("Import Plugin"), width=118, height=34, fg_color=_SURFACE_ALT, hover_color=_CARD_BG, border_width=1, border_color=_CARD_BORDER, corner_radius=12, text_color=_TEXT, command=self._import_plugin).pack(side="left", padx=(10, 0))

        action_row = ctk.CTkFrame(panel, fg_color="transparent")
        action_row.pack(fill="x", padx=18, pady=(0, 16))
        ctk.CTkButton(action_row, text=self._t("Save Settings"), width=146, height=38, fg_color=_ACCENT, hover_color=_ACCENT_HOVER, corner_radius=14, text_color=_TEXT, command=self._save_settings).pack(side="left", padx=(0, 10))

        secondary_actions = ctk.CTkFrame(action_row, fg_color="transparent")
        secondary_actions.pack(side="right")
        for text, cmd in [
            (self._t("Open Log File"), self._open_log_file),
            (self._t("Export Snapshot"), self._export_snapshot),
            (self._t("Import Snapshot"), self._import_snapshot),
            (self._t("Run Organize"), self._run_auto_organize),
            (self._t("Health Scan"), self._run_health_scan),
            (self._t("Companion Feed"), self._generate_companion_feed),
        ]:
            ctk.CTkButton(
                secondary_actions,
                text=text,
                width=132,
                height=38,
                fg_color=_SURFACE_ALT,
                hover_color=_CARD_BG,
                border_width=1,
                border_color=_CARD_BORDER,
                corner_radius=14,
                text_color=_TEXT,
                command=cmd,
            ).pack(side="left", padx=(10, 0))

        self.inline_status = ctk.CTkLabel(self.content, text=f"Log file: {LOG_FILE}", font=ctk.CTkFont(size=12), text_color=_TEXT_SOFT, anchor="w")
        self.inline_status.pack(fill="x", padx=30, pady=(0, 4))

    def _make_settings_field(self, parent: ctk.CTkFrame, *args: Any) -> None:
        if len(args) == 4:
            row, column, label, widget = args
            field = ctk.CTkFrame(parent, fg_color="transparent")
            field.grid(row=row, column=column, sticky="ew", padx=8, pady=8)
        elif len(args) == 2:
            label, widget = args
            field = ctk.CTkFrame(parent, fg_color="transparent")
            field.pack(fill="x", pady=8)
        else:
            raise TypeError("_make_settings_field expects either (row, column, label, widget) or (label, widget)")
        ctk.CTkLabel(field, text=label, font=ctk.CTkFont(size=13, weight="bold"), text_color=_TEXT).pack(anchor="w", pady=(0, 6))
        widget.pack(fill="x")

    def _save_settings(self) -> None:
        try:
            update_settings(
                preferred_format=self.settings_format_var.get(),
                preferred_source=self.settings_source_var.get(),
                default_collection=self.settings_collection_var.get().strip(),
                device_subdir=self.settings_device_subdir_var.get().strip(),
                open_library_after_download=bool(self.settings_open_library_var.get()),
                auto_organize_by=self.settings_organize_var.get(),
                theme_preset=self.settings_theme_var.get(),
                notifications_enabled=bool(self.settings_notifications_var.get()),
                telemetry_enabled=bool(self.settings_telemetry_var.get()),
                interface_language=self.settings_language_var.get(),
                search_cache_enabled=bool(self.settings_cache_var.get()),
                search_cache_max_age_hours=max(1, int(self.settings_cache_age_var.get() or "72")),
                queue_autostart=bool(self.settings_queue_autostart_var.get()),
                workspace_role=self.settings_role_var.get(),
                allowed_actions=self._selected_allowed_actions(),
                active_device_profile=self.settings_profile_var.get(),
                allowed_formats=self._selected_allowed_formats(),
                allowed_sources=self._selected_allowed_sources(),
            )
            self._refresh_settings_cache()
            self._apply_theme_preset(self.settings.get("theme_preset", "Corporate Blue"))
            self._track("settings_saved", language=self.settings.get("interface_language", "English"))
            self._set_status("Settings saved.")
            self._notify("AutoBook", "Settings were updated.")
            self._build_shell_refresh()
        except Exception:
            log_exception("Settings save failed")
            self._set_status("Settings save failed. Check the log for details.")

    def _selected_allowed_sources(self) -> list[str]:
        allowed = []
        if self.allow_gutenberg_var.get():
            allowed.append("Project Gutenberg")
        if self.allow_openlibrary_var.get():
            allowed.append("Open Library")
        if self.allow_external_var.get():
            allowed.append("External")
        return allowed or ["Project Gutenberg", "Open Library"]

    def _selected_allowed_formats(self) -> list[str]:
        allowed = []
        if self.allow_epub_var.get():
            allowed.append("EPUB")
        if self.allow_pdf_var.get():
            allowed.append("PDF")
        return allowed or ["EPUB"]

    def _selected_allowed_actions(self) -> list[str]:
        actions = []
        if self.action_download_var.get():
            actions.append("download")
        if self.action_transfer_var.get():
            actions.append("transfer")
        if self.action_ocr_var.get():
            actions.append("ocr")
        if self.action_convert_var.get():
            actions.append("convert")
        if self.action_ai_var.get():
            actions.append("ai")
        return actions or ["download"]

    def _export_snapshot(self) -> None:
        try:
            path = export_library_snapshot()
            self._track("snapshot_exported", filename=path.name)
            log_info(f"Library snapshot exported path={str(path)!r}")
            self._set_status(f"Snapshot exported to {path.name}.")
            self._notify("AutoBook", f"Snapshot exported to {path.name}.")
        except Exception:
            log_exception("Snapshot export failed")
            self._set_status("Snapshot export failed. Check the log for details.")

    def _generate_companion_feed(self) -> None:
        try:
            path = generate_companion_feed()
            self._track("companion_feed_generated", filename=path.name)
            self._set_status(f"Companion feed generated: {path.name}")
            self._notify("AutoBook", f"Companion feed generated: {path.name}")
        except Exception:
            log_exception("Companion feed generation failed")
            self._set_status("Companion feed generation failed. Check the log for details.")

    def _generate_web_preview(self) -> None:
        try:
            path = export_library_web_preview()
            self._track("web_preview_generated", filename=path.name)
            self._set_status(f"Web preview data generated: {path.name}")
        except Exception:
            log_exception("Web preview generation failed")
            self._set_status("Web preview generation failed. Check the log for details.")

    def _clear_offline_cache(self) -> None:
        try:
            removed = clear_search_cache()
            self._track("cache_cleared", removed=removed)
            self._set_status(f"Cleared {removed} cached search entries.")
            self._show_settings()
        except Exception:
            log_exception("Offline cache cleanup failed")
            self._set_status("Offline cache cleanup failed.")

    def _toggle_plugin(self, plugin_path: str) -> None:
        try:
            plugin = toggle_plugin_enabled(plugin_path)
            self._track("plugin_toggled", plugin=plugin_path)
            self._set_status(f'Plugin updated: {plugin.get("name", plugin_path) if plugin else plugin_path}')
            self._show_settings()
        except Exception:
            log_exception("Plugin toggle failed")
            self._set_status("Plugin toggle failed.")

    def _import_plugin(self) -> None:
        dialog = ctk.CTkInputDialog(text="Enter the full path to a plugin manifest JSON file.", title="Import Plugin")
        path = dialog.get_input()
        if not path:
            return
        try:
            plugin = import_plugin_manifest(path.strip())
            self._track("plugin_imported", plugin=plugin.get("name", "unknown"))
            self._set_status(f'Plugin imported: {plugin.get("name", "unknown")}')
            self._show_settings()
        except Exception as exc:
            log_exception("Plugin import failed")
            self._set_status(f"Plugin import failed: {exc}")

    def _import_snapshot(self) -> None:
        dialog = ctk.CTkInputDialog(text="Enter the full path to an export JSON file.", title="Import Snapshot")
        path = dialog.get_input()
        if not path:
            return
        try:
            result = import_library_snapshot(path.strip())
            self._track("snapshot_imported", imported=result["imported"], skipped=result["skipped"])
            log_info(f"Snapshot import completed imported={result['imported']} skipped={result['skipped']}")
            self._set_status(f"Imported {result['imported']} book(s), skipped {result['skipped']}.")
            self._notify("AutoBook", f"Imported {result['imported']} book(s).")
        except Exception as exc:
            log_exception("Snapshot import failed")
            self._set_status(f"Snapshot import failed: {exc}")

    def _run_auto_organize(self) -> None:
        mode = self.settings_organize_var.get()
        try:
            moved = organize_library_files(mode)
            update_settings(auto_organize_by=mode)
            self._refresh_settings_cache()
            self._track("auto_organize", mode=mode, moved=moved)
            log_info(f"Auto organize completed mode={mode!r} moved={moved}")
            self._set_status(f"Auto organize complete. {moved} file(s) moved.")
            self._notify("AutoBook", f"Auto organize complete. {moved} file(s) moved.")
        except Exception:
            log_exception("Auto organize failed")
            self._set_status("Auto organize failed. Check the log for details.")

    def _run_health_scan(self) -> None:
        try:
            results = scan_library_health()
            issues = [item for item in results if item["status"] != "healthy"]
            self._track("health_scan", issues=len(issues))
            log_info(f"Library health scan completed issues={len(issues)}")
            self._show_health_scan_report(results)
            self._set_status(f"Health scan completed. {len(issues)} issue(s) found.")
        except Exception:
            log_exception("Health scan failed")
            self._set_status("Health scan failed. Check the log for details.")

    def _add_device_profile(self) -> None:
        name = ctk.CTkInputDialog(text="Profile name", title="Add Device Profile").get_input()
        if not name:
            return
        subdir = ctk.CTkInputDialog(text="Default subfolder", title="Add Device Profile").get_input() or ""
        kind = ctk.CTkInputDialog(text="Device kind label", title="Add Device Profile").get_input() or "Generic"
        preferred_format = ctk.CTkInputDialog(text="Preferred format for this profile: Any, EPUB, or PDF", title="Add Device Profile").get_input() or "Any"
        auto_send = (ctk.CTkInputDialog(text="Auto-send after download? yes/no", title="Add Device Profile").get_input() or "no").strip().lower() in {"y", "yes", "true", "1"}
        try:
            save_device_profile(name.strip(), subdir.strip(), kind.strip(), preferred_format.strip().upper() if preferred_format.strip().lower() != "any" else "Any", auto_send)
            self._track("device_profile_saved", name=name.strip())
            self._show_settings()
            self._set_status(f'Profile "{name.strip()}" saved.')
        except Exception:
            log_exception("Device profile save failed")
            self._set_status("Could not save the device profile.")

    def _delete_device_profile_action(self) -> None:
        name = self.settings_profile_var.get().strip()
        if not name:
            return
        try:
            delete_device_profile(name)
            self._track("device_profile_deleted", name=name)
            self._show_settings()
            self._set_status(f'Profile "{name}" deleted.')
        except Exception:
            log_exception("Device profile delete failed")
            self._set_status("Could not delete the device profile.")

    def _show_health_scan_report(self, results: list[dict[str, Any]]) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title(self._t("Library Health Scan"))
        dialog.geometry("720x520")
        dialog.configure(fg_color=_APP_BG)
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text=self._t("Library Health Scan"), font=ctk.CTkFont(size=22, weight="bold"), text_color=_TEXT).pack(anchor="w", padx=20, pady=(18, 8))
        box = ctk.CTkTextbox(dialog, fg_color=_SURFACE, text_color=_TEXT, corner_radius=16, wrap="word")
        box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        issues = [item for item in results if item["status"] != "healthy"]
        if issues:
            ctk.CTkButton(
                dialog,
                text="Attempt Repairs",
                width=140,
                height=36,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOVER,
                corner_radius=12,
                text_color=_TEXT,
                command=lambda: self._repair_from_scan(issues, box),
            ).pack(anchor="e", padx=20, pady=(0, 10))
        if not results:
            box.insert("end", "No library items found.")
            return
        for item in results:
            box.insert("end", f"[{item['status'].upper()}] {item['title']} - {item['message']}\n")

    def _repair_from_scan(self, issues: list[dict[str, Any]], output_box: Any) -> None:
        repaired = 0
        for item in issues:
            try:
                result = repair_book_file(item["id"])
                repaired += 1 if result.get("status") == "repaired" else 0
                output_box.insert("end", f"Repair {item['title']}: {result.get('message', '')}\n")
            except Exception as exc:
                output_box.insert("end", f"Repair {item['title']}: failed - {exc}\n")
        self._track("scan_repair_run", repaired=repaired)
        self._set_status(f"Repair attempt finished. {repaired} item(s) repaired.")

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
