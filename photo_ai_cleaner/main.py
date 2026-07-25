"""Application entry point for Photo AI Cleaner.

Bootstraps logging, loads (or creates) the configuration, starts the Qt
application and shows the main window. Everything runs locally: no server,
no Docker, no WSL, no external database.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from . import __app_name__, __version__
from .gui.main_window import MainWindow
from .utils import paths
from .utils.config import load_config
from .utils.logging_config import configure_logging, get_logger


def _level_from_name(name: str) -> int:
    return getattr(logging, name.upper(), logging.INFO)


def main() -> int:
    """Run the Photo AI Cleaner desktop application."""
    config_path = paths.default_config_path()
    config = load_config(config_path)

    configure_logging(paths.log_dir(), level=_level_from_name(config.log_level))
    logger = get_logger(__name__)
    logger.info("Starting %s v%s", __app_name__, __version__)

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)

    window = MainWindow(config)
    window.show()

    exit_code = app.exec()
    logger.info("Application exited with code %d", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
