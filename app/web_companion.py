"""Local web companion server for AutoBook."""

from __future__ import annotations

import argparse
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.library import (
    get_all_books,
    get_download_history,
    get_library_analytics,
    get_settings,
    get_transfer_history,
    search_books_in_library,
)
from app.logging_utils import log_exception, log_info

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"

_server_lock = threading.Lock()
_server_instance: ThreadingHTTPServer | None = None
_server_thread: threading.Thread | None = None


def _json_payload() -> dict[str, Any]:
    return {
        "books": get_all_books(),
        "analytics": get_library_analytics(),
        "download_history": get_download_history(limit=40),
        "transfer_history": get_transfer_history(limit=20),
        "settings": get_settings(),
    }


class CompanionHandler(BaseHTTPRequestHandler):
    server_version = "AutoBookCompanion/0.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        log_info("Web companion: " + format % args)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            route = parsed.path
            if route == "/api/payload":
                self._send_json(_json_payload())
                return
            if route == "/api/search":
                query = parse_qs(parsed.query).get("q", [""])[0]
                self._send_json(search_books_in_library(query=query))
                return
            if route == "/api/health":
                self._send_json({"ok": True})
                return
            if route in {"/", "/index.html"}:
                self._serve_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
                return
            if route == "/app.js":
                self._serve_file(WEB_DIR / "app.js", "application/javascript; charset=utf-8")
                return
            if route == "/styles.css":
                self._serve_file(WEB_DIR / "styles.css", "text/css; charset=utf-8")
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception:
            log_exception("Web companion request failed")
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)


def start_server(host: str = "127.0.0.1", port: int = 8765) -> str:
    global _server_instance, _server_thread
    with _server_lock:
        if _server_instance is not None:
            return f"http://{host}:{_server_instance.server_port}"
        server = ThreadingHTTPServer((host, port), CompanionHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True, name="autobook-web-companion")
        thread.start()
        _server_instance = server
        _server_thread = thread
        log_info(f"Web companion started host={host!r} port={server.server_port}")
        return f"http://{host}:{server.server_port}"


def stop_server() -> None:
    global _server_instance, _server_thread
    with _server_lock:
        if _server_instance is None:
            return
        _server_instance.shutdown()
        _server_instance.server_close()
        _server_instance = None
        _server_thread = None
        log_info("Web companion stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AutoBook local web companion.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    url = start_server(args.host, args.port)
    print(url)
    try:
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        stop_server()


if __name__ == "__main__":
    main()
