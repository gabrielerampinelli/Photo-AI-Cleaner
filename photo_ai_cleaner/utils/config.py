"""Load and persist the :class:`AppConfig` from ``config.json``."""

from __future__ import annotations

import json
from pathlib import Path

from ..models.data_models import AppConfig
from .logging_config import get_logger

_logger = get_logger(__name__)


def load_config(path: Path) -> AppConfig:
    """Load configuration from ``path``, creating defaults if missing."""
    if not path.exists():
        _logger.info("No config found at %s - creating default config", path)
        config = AppConfig()
        save_config(config, path)
        return config
    try:
        # utf-8-sig tolerates a UTF-8 BOM, which some editors (and Windows
        # PowerShell) prepend and which plain utf-8 decoding would reject.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        config = AppConfig.from_dict(data)
        _logger.info("Loaded configuration from %s", path)
        return config
    except (json.JSONDecodeError, OSError, TypeError) as exc:
        _logger.error("Failed to read config %s: %s - using defaults", path, exc)
        return AppConfig()


def save_config(config: AppConfig, path: Path) -> None:
    """Persist the configuration to ``path`` as pretty-printed JSON."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(config.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _logger.info("Saved configuration to %s", path)
    except OSError as exc:
        _logger.error("Failed to save config %s: %s", path, exc)
