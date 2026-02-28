#!/usr/bin/env python3
"""AutoBook – Desktop e-book downloader.  Run with: uv run main.py"""

from __future__ import annotations

import io
import platform
import subprocess
import threading
from pathlib import Path
from typing import Any

import customtkinter as ctk
import requests
from PIL import Image

from app.devices import copy_to_device, detect_devices
from app.library import (
    LIBRARY_DIR, add_to_library, get_all_books, get_book_path, remove_from_library,
)
from app.search import BookResult, resolve_external_download, search_books

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Girly palette ───────────────────────────────────────────
_PINK       = "#e75480"       # primary accent
_PINK_HOVER = "#d63e6c"       # button hover
_ROSE       = "#b34d6d"       # sidebar bg
_ROSE_DARK  = "#8c3a55"       # sidebar hover
_LAVENDER   = "#c9a0dc"       # info text
_BLUSH      = "#f5e6f0"       # light text on dark
_MAUVE      = "#2d1f2d"       # card / frame bg
_BG_DARK    = "#1a0f1a"       # main window bg
_GOLD       = "#e8b4b8"       # secondary accent
_SOFT_GRAY  = "#dda0dd"       # muted text (plum)

_UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}


def _load_cover(url: str, size: tuple[int, int] = (100, 150)) -> ctk.CTkImage | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=8, headers=_UA)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)
    except Exception:
        return None


def _safe_filename(title: str, fmt: str) -> str:
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:80].strip()
    return f"{safe}.{fmt}" if safe else f"book.{fmt}"


def _rating_stars(rating: float) -> str:
    """Convert a 0-5 rating to a star string like ★★★★☆."""
    full = int(rating)
    half = 1 if rating - full >= 0.3 else 0
    empty = 5 - full - half
    return "★" * full + ("½" if half else "") + "☆" * empty

import tkinter as tk


class ScrollableFrame(tk.Frame):
    """Text-widget-based scrollable container.

    Tk 9.0 on macOS does not fire <MouseWheel> events, so the Canvas-based
    CTkScrollableFrame cannot scroll with the trackpad.  The tk.Text widget
    *does* support native trackpad scrolling even with embedded windows,
    so we use it as the scroll container instead.
    """

    def __init__(self, master, fg_color=_BG_DARK, **kw):
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

        # Inner frame that callers pack widgets into
        self.inner = tk.Frame(self._text, bg=fg_color)
        self._text.configure(state="normal")
        self._text.window_create("1.0", window=self.inner, stretch=True)
        self._text.configure(state="disabled")

        # Re-sync the embedded window width when the Text resizes
        self._text.bind("<Configure>", self._on_resize)

    # Expose winfo_children on inner so card iteration works
    def winfo_children(self):
        return self.inner.winfo_children()

    def _on_resize(self, _event=None):
        # Make the inner frame fill the text widget width
        w = self._text.winfo_width() - 6  # small padding
        if w > 10:
            self.inner.configure(width=w)

class AutoBookApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("✿ AutoBook ✿")
        self.geometry("1050x700")
        self.minsize(800, 500)
        self.configure(fg_color=_BG_DARK)

        self._image_refs: list[ctk.CTkImage] = []

        # Sidebar
        sb = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color=_ROSE)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)
        ctk.CTkLabel(sb, text="🌸 AutoBook",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=_BLUSH).pack(padx=20, pady=(25, 30))
        for txt, cmd in [("🔍  Search", self._show_search),
                         ("💖  Library", self._show_library),
                         ("📱  Devices", self._show_devices)]:
            ctk.CTkButton(sb, text=txt, command=cmd, height=38,
                          fg_color=_ROSE_DARK, hover_color=_PINK,
                          text_color=_BLUSH, corner_radius=12,
                          ).pack(padx=15, pady=5, fill="x")

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=_BG_DARK)
        self.content.pack(side="right", fill="both", expand=True)
        self.inline_status: ctk.CTkLabel | None = None
        self._show_search()

    def _clear_content(self) -> None:
        self._image_refs.clear()
        self.inline_status = None
        for w in self.content.winfo_children():
            w.destroy()

    def _set_status(self, msg: str) -> None:
        if self.inline_status:
            try: self.inline_status.configure(text=msg)
            except Exception: pass

    def _load_cover_async(self, url: str, label: ctk.CTkLabel,
                          size: tuple[int, int] = (100, 150)) -> None:
        """Load a cover image in a background thread and update *label*."""
        def _work(u: str = url, lbl: ctk.CTkLabel = label) -> None:
            img = _load_cover(u, size)
            if img:
                self._image_refs.append(img)
                self.after(0, lambda: _apply(img, lbl))
        def _apply(i: ctk.CTkImage, l: ctk.CTkLabel) -> None:
            try: l.configure(image=i, text="")
            except Exception: pass
        threading.Thread(target=_work, daemon=True).start()

    # ── Search page ─────────────────────────────────────────────────

    def _show_search(self) -> None:
        self._clear_content()

        top = ctk.CTkFrame(self.content, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(15, 5))

        ctk.CTkLabel(top, text="✨ Search for e-books",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=_BLUSH).pack(side="left")

        search_row = ctk.CTkFrame(self.content, fg_color="transparent")
        search_row.pack(fill="x", padx=20, pady=10)

        self.search_entry = ctk.CTkEntry(search_row,
                                         placeholder_text="Book title, author name, or keyword…",
                                         height=38, corner_radius=16,
                                         border_color=_PINK,
                                         fg_color=_MAUVE,
                                         text_color=_BLUSH)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<Return>", lambda e: self._do_search())

        ctk.CTkButton(search_row, text="🔍 Search", width=100, height=38,
                      fg_color=_PINK, hover_color=_PINK_HOVER,
                      corner_radius=16,
                      command=self._do_search).pack(side="right")

        # Inline status line
        self.inline_status = ctk.CTkLabel(self.content, text="",
                                          font=ctk.CTkFont(size=12),
                                          text_color=_SOFT_GRAY, anchor="w")
        self.inline_status.pack(fill="x", padx=22, pady=(0, 2))

        # Scrollable results area
        self.results_frame = ScrollableFrame(self.content, fg_color=_BG_DARK)
        self.results_frame.pack(fill="both", expand=True, padx=20, pady=(5, 15))

        self.search_entry.focus()

    def _do_search(self) -> None:
        query = self.search_entry.get().strip()
        if not query:
            return

        # Clear old results
        for w in self.results_frame.winfo_children():
            w.destroy()

        self._set_status(f"🌸 Searching for \"{query}\"…")
        self.update_idletasks()

        # Run search in background thread
        def _worker() -> None:
            results = search_books(query)
            self.after(0, lambda: self._display_results(results, query))

        threading.Thread(target=_worker, daemon=True).start()

    def _display_results(self, results: list[BookResult], query: str) -> None:
        for w in self.results_frame.winfo_children():
            w.destroy()

        self._set_status(f"✿ Found {len(results)} results for \"{query}\"")

        if not results:
            ctk.CTkLabel(self.results_frame.inner,
                         text="No results found 💔\nTry a different title, author, or keyword.",
                         font=ctk.CTkFont(size=14), text_color=_SOFT_GRAY).pack(pady=30)
            return

        for book in results:
            self._make_search_card(book)

    def _make_search_card(self, book: BookResult) -> None:
        card = ctk.CTkFrame(self.results_frame.inner, corner_radius=14,
                            fg_color=_MAUVE, border_width=1, border_color=_ROSE)
        card.pack(fill="x", pady=4, padx=2)

        cover = ctk.CTkLabel(card, text="📕", width=100, height=120,
                             font=ctk.CTkFont(size=36))
        cover.pack(side="left", padx=(10, 5), pady=8)
        if book.cover_url:
            self._load_cover_async(book.cover_url, cover)

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        ctk.CTkLabel(info, text=book.title, font=ctk.CTkFont(size=15, weight="bold"),
                     anchor="w", wraplength=400, text_color=_BLUSH).pack(anchor="w")
        # Star rating
        if book.rating > 0:
            stars = _rating_stars(book.rating)
            rating_text = f"{stars}  {book.rating:.1f}  ({book.ratings_count})"
            ctk.CTkLabel(info, text=rating_text, font=ctk.CTkFont(size=12),
                         text_color=_GOLD, anchor="w").pack(anchor="w", pady=(1, 0))
        subtitle = " ♡ ".join(filter(None, [book.author, book.year]))
        if subtitle:
            ctk.CTkLabel(info, text=subtitle, font=ctk.CTkFont(size=12),
                         text_color=_SOFT_GRAY, anchor="w").pack(anchor="w", pady=(2, 0))
        src = f"{book.source}  ·  {book.language}" if book.language else book.source
        ctk.CTkLabel(info, text=src, font=ctk.CTkFont(size=11),
                     text_color=_LAVENDER, anchor="w").pack(anchor="w", pady=(2, 0))

        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=10, pady=8)
        for dl in book.downloads:
            ctk.CTkButton(
                btn_frame, text=f"♡ {dl.format.upper()}  ({dl.mirror})",
                width=200, height=30, fg_color=_PINK, hover_color=_PINK_HOVER,
                corner_radius=12,
                command=lambda d=dl, b=book: self._download_book(d, b),
            ).pack(pady=2)
        if not book.downloads:
            ctk.CTkLabel(btn_frame, text="No direct download", text_color=_SOFT_GRAY).pack()

    def _download_book(self, dl: Any, book: BookResult) -> None:
        self._set_status(f"💫 Downloading {book.title} ({dl.format.upper()})…")
        self.update_idletasks()

        # Build ordered list: clicked link first, then same-format alternatives
        candidates = [dl] + [
            d for d in book.downloads
            if d.url != dl.url and d.format == dl.format
        ]

        def _try_download(link: Any) -> requests.Response | None:
            """Attempt a single download link; return response or None."""
            urls = [link.url]
            # Resolve ads.php → get.php with key
            if "/ads.php?md5=" in link.url:
                resolved = resolve_external_download(link.url)
                if resolved:
                    urls = [resolved]
                else:
                    return None
            # For IA links, also try alternate mirror
            elif "archive.org" in link.url:
                alt = link.url.replace("//dn", "//ia").replace(
                    ".ca.archive.org", ".us.archive.org")
                if alt != link.url:
                    urls.append(alt)
            for url in urls:
                try:
                    resp = requests.get(url, stream=True, timeout=60,
                                        headers=_UA, allow_redirects=True)
                    if resp.status_code >= 400:
                        resp.close()
                        continue
                    ct = resp.headers.get("Content-Type", "")
                    if "text/html" in ct and link.format in ("epub", "pdf"):
                        resp.close()
                        continue
                    return resp
                except requests.RequestException:
                    continue
            return None

        def _worker() -> None:
            for candidate in candidates:
                resp = _try_download(candidate)
                if resp is None:
                    continue
                try:
                    fname = _safe_filename(book.title, candidate.format)
                    dest = LIBRARY_DIR / fname
                    n = 1
                    while dest.exists():
                        fname = _safe_filename(f"{book.title}_{n}", candidate.format)
                        dest = LIBRARY_DIR / fname
                        n += 1
                    with open(dest, "wb") as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
                    add_to_library(fname, book.title, book.author,
                                   candidate.format, book.cover_url, book.source)
                    self.after(0, lambda: self._set_status(
                        f'💖 "{book.title}" downloaded!'))
                    return
                except Exception as exc:
                    # Write failed – clean up partial file and try next
                    if dest.exists():
                        dest.unlink(missing_ok=True)
                    continue
                finally:
                    resp.close()

            # All candidates exhausted
            self.after(0, lambda: self._set_status(
                f"💔 Download failed – all sources returned errors"))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Library page ────────────────────────────────────────────────

    def _show_library(self) -> None:
        self._clear_content()

        top = ctk.CTkFrame(self.content, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(15, 10))

        ctk.CTkLabel(top, text="💖 My Library",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=_BLUSH).pack(side="left")

        ctk.CTkButton(top, text="⟳ Refresh", width=90, height=32,
                      fg_color=_PINK, hover_color=_PINK_HOVER,
                      corner_radius=12,
                      command=self._show_library).pack(side="right")

        # Inline status line
        self.inline_status = ctk.CTkLabel(self.content, text="",
                                          font=ctk.CTkFont(size=12),
                                          text_color=_SOFT_GRAY, anchor="w")
        self.inline_status.pack(fill="x", padx=22, pady=(0, 2))

        books = get_all_books()

        if not books:
            ctk.CTkLabel(self.content,
                         text="Your library is empty 🌸\nSearch and download some books!",
                         font=ctk.CTkFont(size=16), text_color=_SOFT_GRAY).pack(pady=60)
            return

        scroll = ScrollableFrame(self.content, fg_color=_BG_DARK)
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        for book in books:
            self._make_library_card(scroll.inner, book)

    def _make_library_card(self, parent: ctk.CTkFrame, book: dict[str, Any]) -> None:
        card = ctk.CTkFrame(parent, corner_radius=14,
                            fg_color=_MAUVE, border_width=1, border_color=_ROSE)
        card.pack(fill="x", pady=4, padx=2)

        cover = ctk.CTkLabel(card, text="📖", width=80, height=100,
                             font=ctk.CTkFont(size=30))
        cover.pack(side="left", padx=(10, 5), pady=8)
        if book.get("cover_url"):
            self._load_cover_async(book["cover_url"], cover, (80, 110))

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        ctk.CTkLabel(info, text=book.get("title", "Unknown"),
                     font=ctk.CTkFont(size=14, weight="bold"),
                     anchor="w", wraplength=350, text_color=_BLUSH).pack(anchor="w")
        if book.get("author"):
            ctk.CTkLabel(info, text=book["author"], font=ctk.CTkFont(size=12),
                         text_color=_SOFT_GRAY, anchor="w").pack(anchor="w")
        ctk.CTkLabel(info, text=f"Format: {book.get('format', '').upper()}",
                     font=ctk.CTkFont(size=11), text_color=_LAVENDER,
                     anchor="w").pack(anchor="w", pady=(2, 0))

        bf = ctk.CTkFrame(card, fg_color="transparent")
        bf.pack(side="right", padx=10, pady=8)
        ctk.CTkButton(bf, text="📂 Open", width=100, height=30,
                      fg_color=_PINK, hover_color=_PINK_HOVER, corner_radius=12,
                      command=lambda b=book: self._open_book_file(b)).pack(pady=2)
        ctk.CTkButton(bf, text="📱 Send", width=100, height=30,
                      fg_color=_ROSE_DARK, hover_color=_ROSE, corner_radius=12,
                      command=lambda b=book: self._send_to_device(b)).pack(pady=2)
        ctk.CTkButton(bf, text="🗑 Remove", width=100, height=30,
                      fg_color="#6b2039", hover_color="#8b2a4a", corner_radius=12,
                      command=lambda b=book: self._delete_book(b)).pack(pady=2)

    def _open_book_file(self, book: dict[str, Any]) -> None:
        path = get_book_path(book["id"])
        if not path:
            self._set_status("💔 File not found"); return
        cmd = {"Darwin": ["open", "-R"], "Linux": ["xdg-open"]}.get(
            platform.system(), ["explorer"])
        subprocess.Popen([*cmd, str(path if cmd[0] == "open" else path.parent)])

    def _delete_book(self, book: dict[str, Any]) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("Confirm Delete")
        dlg.geometry("360x150")
        dlg.configure(fg_color=_MAUVE)
        dlg.transient(self); dlg.grab_set()
        ctk.CTkLabel(dlg, text=f"Remove \"{book.get('title')}\"? 🥺",
                     font=ctk.CTkFont(size=14), wraplength=320,
                     text_color=_BLUSH).pack(pady=(20, 10))
        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(pady=10)
        def _confirm():
            remove_from_library(book["id"]); dlg.destroy()
            self._show_library(); self._set_status(f"Removed \"{book.get('title')}\"")
        ctk.CTkButton(row, text="Remove", fg_color="#6b2039",
                      hover_color="#8b2a4a", corner_radius=12,
                      command=_confirm).pack(side="left", padx=5)
        ctk.CTkButton(row, text="Cancel", fg_color=_ROSE_DARK,
                      hover_color=_ROSE, corner_radius=12,
                      command=dlg.destroy).pack(side="left", padx=5)

    def _send_to_device(self, book: dict[str, Any]) -> None:
        devices = detect_devices()
        if not devices:
            self._set_status("💔 No devices connected – go to Devices tab")
            return
        if len(devices) == 1:
            self._do_transfer(book, devices[0])
        else:
            self._show_device_picker(book, devices)

    def _show_device_picker(self, book: dict[str, Any], devices: list) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("Choose Device")
        dlg.geometry("340x300")
        dlg.configure(fg_color=_MAUVE)
        dlg.transient(self); dlg.grab_set()
        ctk.CTkLabel(dlg, text="Send to which device? ✨",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=_BLUSH).pack(pady=(15, 10))
        for dev in devices:
            icon = {"ipad": "📱", "ereader": "📖", "mtp": "📖"}.get(dev.kind, "💾")
            ctk.CTkButton(
                dlg, text=f"{icon}  {dev.name}", height=36,
                fg_color=_PINK, hover_color=_PINK_HOVER, corner_radius=12,
                command=lambda d=dev: (dlg.destroy(), self._do_transfer(book, d)),
            ).pack(padx=20, pady=3, fill="x")

    def _do_transfer(self, book: dict[str, Any], device: Any) -> None:
        path = get_book_path(book["id"])
        if not path:
            self._set_status("💔 File not found in library"); return
        try:
            self._set_status(f"💖 Sent to {device.name}: {copy_to_device(str(path), device)}")
        except Exception as exc:
            self._set_status(f"💔 Transfer failed: {exc}")

    # ── Devices page ────────────────────────────────────────────────

    def _show_devices(self) -> None:
        self._clear_content()

        top = ctk.CTkFrame(self.content, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(15, 10))

        ctk.CTkLabel(top, text="📱 Connected Devices",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=_BLUSH).pack(side="left")

        ctk.CTkButton(top, text="⟳ Scan", width=90, height=32,
                      fg_color=_PINK, hover_color=_PINK_HOVER,
                      corner_radius=12,
                      command=self._show_devices).pack(side="right")

        # Inline status line
        self.inline_status = ctk.CTkLabel(self.content, text="🔍 Scanning for devices…",
                                          font=ctk.CTkFont(size=12),
                                          text_color=_SOFT_GRAY, anchor="w")
        self.inline_status.pack(fill="x", padx=22, pady=(0, 2))
        self.update_idletasks()

        devices = detect_devices()

        if not devices:
            from app.devices import _has_mtp_tools
            mtp_ok = _has_mtp_tools()
            is_sequoia = platform.system() == "Darwin" and int(platform.mac_ver()[0].split(".")[0]) >= 13

            msg = ("No e-readers or tablets detected 💔\n\n"
                   "• Use a data cable (not charge-only)\n"
                   "• Unlock the device and accept any USB prompt\n"
                   "• Connect iPad → trust this computer")

            if is_sequoia:
                msg += ("\n\n🔒 macOS USB Security\n"
                        "macOS may block new USB accessories.\n"
                        "Go to System Settings → Privacy & Security\n"
                        "→ scroll down → set \"Allow accessories to\n"
                        "connect\" to \"Automatically When Unlocked\".\n"
                        "Then unplug & replug the cable.")

            if not mtp_ok:
                msg += ("\n\n⚠ MTP support not installed.\n"
                        "Newer Kindles (fw 5.16+) need MTP. Click below.")

            ctk.CTkLabel(self.content, text=msg,
                         font=ctk.CTkFont(size=14), text_color=_SOFT_GRAY,
                         justify="left").pack(pady=(20, 10), padx=30, anchor="w")

            btn_row = ctk.CTkFrame(self.content, fg_color="transparent")
            btn_row.pack(fill="x", padx=30, pady=5, anchor="w")

            if not mtp_ok:
                ctk.CTkButton(
                    btn_row, text="📦 Install MTP Support",
                    width=200, height=36,
                    fg_color=_PINK, hover_color=_PINK_HOVER,
                    corner_radius=12,
                    command=self._install_mtp,
                ).pack(side="left", padx=(0, 8))

            ctk.CTkButton(
                btn_row, text="🔌 USB Troubleshooter",
                width=190, height=36,
                fg_color=_ROSE, hover_color=_ROSE_DARK,
                corner_radius=12,
                command=self._run_usb_troubleshoot,
            ).pack(side="left", padx=(0, 8))

            self._set_status("No devices found 💔")
            return

        self._set_status(f"✨ Found {len(devices)} device(s)")

        scroll = ScrollableFrame(self.content, fg_color=_BG_DARK)
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        _KIND = {
            "ereader": ("📖", "E-Reader"),
            "ipad": ("📱", "iPad / iPhone"),
            "mtp": ("📖", "E-Reader (MTP)"),
        }
        for dev in devices:
            card = ctk.CTkFrame(scroll.inner, corner_radius=14,
                                fg_color=_MAUVE, border_width=1, border_color=_ROSE)
            card.pack(fill="x", pady=4, padx=2)
            icon, kind_name = _KIND.get(dev.kind, ("💾", "USB Drive"))
            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=32),
                         width=60).pack(side="left", padx=10, pady=10)
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, padx=8, pady=10)
            ctk.CTkLabel(info, text=dev.name, font=ctk.CTkFont(size=15, weight="bold"),
                         anchor="w", text_color=_BLUSH).pack(anchor="w")
            ctk.CTkLabel(info, text=kind_name, font=ctk.CTkFont(size=12),
                         text_color=_SOFT_GRAY, anchor="w").pack(anchor="w")
            if dev.mount_point:
                path_text = f"Path: {dev.mount_point}"
                path_color = _LAVENDER
            elif dev.kind == "mtp":
                path_text = "Connected via MTP – file transfer supported ✓"
                path_color = _LAVENDER
            else:
                path_text = "Not directly mountable – use Finder/iTunes"
                path_color = _GOLD
            ctk.CTkLabel(info, text=path_text, font=ctk.CTkFont(size=11),
                         text_color=path_color, anchor="w").pack(anchor="w")
            if dev.status:
                ctk.CTkLabel(info, text=f"⚠ {dev.status}",
                             font=ctk.CTkFont(size=11),
                             text_color=_GOLD, anchor="w",
                             wraplength=350).pack(anchor="w", pady=(2, 0))

    def _install_mtp(self) -> None:
        """Install libmtp via Homebrew for MTP device support."""
        import shutil as _shutil
        if not _shutil.which("brew"):
            self._set_status("💔 Homebrew not found – install from brew.sh first")
            return
        self._set_status("📦 Installing MTP support…")
        self.update_idletasks()

        def _do_install() -> None:
            try:
                import subprocess as _sp
                _sp.run(["brew", "install", "libmtp"],
                        capture_output=True, timeout=120)
                self.after(0, lambda: (
                    self._set_status("✨ MTP support installed! Click Scan."),
                ))
            except Exception as e:
                self.after(0, lambda: self._set_status(f"💔 Install failed: {e}"))

        threading.Thread(target=_do_install, daemon=True).start()

    # ── USB Troubleshooter ──────────────────────────────────────────

    def _run_usb_troubleshoot(self) -> None:
        """Run USB diagnostics and show results in a dialog."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("USB Troubleshooter")
        dlg.geometry("520x440")
        dlg.configure(fg_color=_BG_DARK)
        dlg.transient(self); dlg.grab_set()

        ctk.CTkLabel(dlg, text="🔌 USB Troubleshooter",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=_BLUSH).pack(pady=(15, 5))

        result_text = ctk.CTkTextbox(dlg, fg_color=_MAUVE, text_color=_BLUSH,
                                     font=ctk.CTkFont(family="Menlo", size=12),
                                     corner_radius=10, wrap="word")
        result_text.pack(fill="both", expand=True, padx=15, pady=10)
        result_text.insert("end", "Running diagnostics…\n")
        dlg.update_idletasks()

        def _diagnose() -> str:
            lines: list[str] = []
            # 1. USB bus
            try:
                out = subprocess.check_output(
                    ["system_profiler", "SPUSBDataType", "-detailLevel", "mini"],
                    text=True, timeout=5)
                usb_devs = [l.strip().rstrip(":") for l in out.splitlines()
                            if l.strip().endswith(":") and ":" not in l.strip()[:-1]
                            and "USB" not in l.strip() and "Host" not in l.strip()]
                if usb_devs:
                    lines.append(f"✅ USB devices found: {', '.join(usb_devs)}")
                else:
                    lines.append("❌ No USB devices found on the bus")

                has_kindle = any("kindle" in d.lower() or "amazon" in d.lower()
                                 for d in usb_devs)
                if has_kindle:
                    lines.append("✅ Kindle detected on USB bus!")
                else:
                    lines.append("❌ Kindle NOT on USB bus")
            except Exception:
                lines.append("⚠ Could not scan USB bus")

            # 2. MTP tools
            import shutil
            if shutil.which("mtp-detect"):
                lines.append("✅ libmtp is installed")
                try:
                    out = subprocess.check_output(
                        ["mtp-detect"], text=True, stderr=subprocess.STDOUT,
                        timeout=10)
                    if "1949" in out or "kindle" in out.lower() or "amazon" in out.lower():
                        lines.append("✅ Kindle found via MTP!")
                    elif "No raw devices" in out:
                        lines.append("❌ mtp-detect: No MTP devices found")
                    else:
                        lines.append(f"⚠ mtp-detect: {out.strip()[:100]}")
                except Exception:
                    lines.append("⚠ mtp-detect timed out")
            else:
                lines.append("❌ libmtp not installed (run: brew install libmtp)")

            # 3. Mounted volumes
            vols = [v for v in Path("/Volumes").iterdir()
                    if v.is_dir() and v.name.lower() not in
                    {"macintosh hd", "macintosh hd - data", "recovery"}]
            if vols:
                lines.append(f"✅ Mounted volumes: {', '.join(v.name for v in vols)}")
            else:
                lines.append("❌ No external volumes mounted")

            # 4. macOS USB security
            try:
                ver = int(platform.mac_ver()[0].split(".")[0])
                if ver >= 13:
                    lines.append("")
                    lines.append("🔒 macOS USB Accessory Security is active")
                    lines.append("   This may silently block new USB devices.")
                    lines.append("   Fix: System Settings → Privacy & Security")
                    lines.append('   → "Allow accessories" → "Automatically"')
                    lines.append("   Then unplug & replug the Kindle.")
            except Exception:
                pass

            # 5. General tips
            lines.append("")
            lines.append("📋 Troubleshooting steps:")
            lines.append("  1. Use the ORIGINAL Kindle USB cable")
            lines.append("  2. Plug directly into Mac (no hub/adapter)")
            lines.append("  3. Unlock the Kindle screen")
            lines.append("  4. If using USB-C adapter, try a different one")
            lines.append("  5. Restart the Kindle (hold power 20s)")
            lines.append("  6. Try a different USB port")
            lines.append("")
            lines.append("💌 Alternative: Use Send-to-Kindle email")
            lines.append("   (set up in the Devices tab below)")

            return "\n".join(lines)

        def _run() -> None:
            report = _diagnose()
            self.after(0, lambda: (
                result_text.delete("1.0", "end"),
                result_text.insert("end", report),
            ))

        threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    AutoBookApp().mainloop()
