"""Worker that fetches and decodes a thumbnail on demand.

Thumbnails are pulled from the phone only when a result needs to be shown,
cached in RAM (LRU) and emitted back to the GUI thread via a signal.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from ..adb.adb_client import AdbClient
from ..cache.thumbnail_cache import ThumbnailCache
from ..utils.image_utils import make_thumbnail
from ..utils.logging_config import get_logger

_logger = get_logger(__name__)


class _ThumbSignals(QObject):
    """Signals for :class:`ThumbnailWorker`."""

    ready = Signal(str, bytes)  # phone_path, jpeg bytes
    failed = Signal(str)  # phone_path


class ThumbnailWorker(QRunnable):
    """Fetch a single thumbnail (from cache or phone) off the GUI thread."""

    def __init__(
        self,
        adb: AdbClient,
        cache: ThumbnailCache,
        phone_path: str,
        max_side: int = 256,
    ) -> None:
        super().__init__()
        self._adb = adb
        self._cache = cache
        self._path = phone_path
        self._max_side = max_side
        self.signals = _ThumbSignals()

    def run(self) -> None:  # noqa: D401 - Qt entry point
        """Return a cached thumbnail or fetch, resize and cache one."""
        cached = self._cache.get(self._path)
        if cached is not None:
            self.signals.ready.emit(self._path, cached)
            return

        data = self._adb.read_file(self._path)
        if not data:
            self.signals.failed.emit(self._path)
            return

        thumb = make_thumbnail(data, self._max_side)
        if thumb is None:
            self.signals.failed.emit(self._path)
            return

        self._cache.put(self._path, thumb)
        self.signals.ready.emit(self._path, thumb)
