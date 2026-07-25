"""Centralised logging configuration.

Provides detailed logging across the whole application with the standard
levels (DEBUG, INFO, WARNING, ERROR). Logs are written both to the console
and to a rotating log file inside the application data directory.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(
    log_dir: Path,
    level: int = logging.INFO,
    console: bool = True,
) -> None:
    """Configure root logging for the whole application.

    Args:
        log_dir: Directory in which the rotating log file is stored.
        level: Minimum log level to emit.
        console: Whether to additionally log to stderr.
    """
    global _configured
    if _configured:
        logging.getLogger().setLevel(level)
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "photo_ai_cleaner.log"

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root.addHandler(console_handler)

    _configured = True
    logging.getLogger(__name__).info("Logging configured (level=%s)", logging.getLevelName(level))


def get_logger(name: str) -> logging.Logger:
    """Return a module level logger."""
    return logging.getLogger(name)
