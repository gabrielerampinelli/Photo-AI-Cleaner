"""Worker that streams a full-resolution image into memory for viewing.

Unlike :class:`ThumbnailWorker`, this fetches the original bytes (no resize)
so the in-app viewer can show the photo at full quality. Nothing is written
to disk - the bytes live only in RAM for the lifetime of the viewer.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from ..adb.adb_client import AdbClient
from ..utils.logging_config import get_logger

_logger = get_logger(__name__)


class _FullImageSignals(QObject):
    """Signals for :class:`FullImageWorker`."""

    ready = Signal(str, bytes)  # phone_path, original image bytes
    failed = Signal(str)  # phone_path


class FullImageWorker(QRunnable):
    """Fetch a single full-resolution image off the GUI thread."""

    def __init__(self, adb: AdbClient, phone_path: str) -> None:
        super().__init__()
        self._adb = adb
        self._path = phone_path
        self.signals = _FullImageSignals()

    def run(self) -> None:  # noqa: D401 - Qt entry point
        """Stream the original image bytes and emit them."""
        data = self._adb.read_file(self._path)
        if data:
            self.signals.ready.emit(self._path, data)
        else:
            self.signals.failed.emit(self._path)
