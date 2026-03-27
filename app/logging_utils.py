"""Central logging helpers for AutoBook."""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "autobook.log"


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger("autobook")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False

    def _excepthook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return sys.__excepthook__(exc_type, exc_value, exc_traceback)
        logger.exception("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

    def _threading_excepthook(args: threading.ExceptHookArgs) -> None:
        logger.exception(
            "Unhandled thread exception in %s",
            args.thread.name if args.thread else "unknown-thread",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _excepthook
    threading.excepthook = _threading_excepthook
    logger.info("Logging initialized")
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("autobook")


def log_exception(message: str) -> None:
    get_logger().exception(message)


def log_info(message: str) -> None:
    get_logger().info(message)
