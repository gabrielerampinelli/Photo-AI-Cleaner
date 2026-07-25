"""Application filesystem paths.

Centralises where the app stores its data (database, config, logs, model
cache) so that no module hard-codes locations. Everything lives under a
per-user application data directory, keeping the tool fully local.
"""

from __future__ import annotations

import os
from pathlib import Path


def app_data_dir() -> Path:
    """Return the base directory for all application data.

    On Windows this resolves to ``%LOCALAPPDATA%\\PhotoAICleaner``; on other
    platforms it falls back to ``~/.photo_ai_cleaner``.
    """
    base = os.environ.get("LOCALAPPDATA")
    if base:
        path = Path(base) / "PhotoAICleaner"
    else:
        path = Path.home() / ".photo_ai_cleaner"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    """Return the SQLite database file path."""
    return app_data_dir() / "photos.db"


def index_path() -> Path:
    """Return the FAISS index file path."""
    return app_data_dir() / "vectors.faiss"


def log_dir() -> Path:
    """Return the directory used for log files."""
    return app_data_dir() / "logs"


def default_config_path() -> Path:
    """Return the path of the user configuration file."""
    return app_data_dir() / "config.json"


def model_cache_dir() -> Path:
    """Return the directory used to cache downloaded AI model weights."""
    path = app_data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path
