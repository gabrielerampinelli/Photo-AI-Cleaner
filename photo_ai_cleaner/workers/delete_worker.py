"""Worker that deletes selected images from the phone and the database."""

from __future__ import annotations

from typing import List

from PySide6.QtCore import QObject, QRunnable, Signal

from ..adb.adb_client import AdbClient
from ..cache.thumbnail_cache import ThumbnailCache
from ..database.db import Database
from ..search.vector_index import VectorIndex
from ..utils.logging_config import get_logger

_logger = get_logger(__name__)


class _DeleteSignals(QObject):
    """Signals for :class:`DeleteWorker`."""

    finished = Signal(list)  # list of successfully deleted phone paths
    error = Signal(str)


class DeleteWorker(QRunnable):
    """Delete images on the device, then purge DB, index and cache entries."""

    def __init__(
        self,
        adb: AdbClient,
        database: Database,
        index: VectorIndex,
        cache: ThumbnailCache,
        rowids: List[int],
        phone_paths: List[str],
    ) -> None:
        super().__init__()
        self._adb = adb
        self._db = database
        self._index = index
        self._cache = cache
        self._rowids = rowids
        self._phone_paths = phone_paths
        self.signals = _DeleteSignals()

    def run(self) -> None:  # noqa: D401 - Qt entry point
        """Perform the deletion and keep all stores consistent."""
        try:
            removed = self._adb.delete_files(self._phone_paths)
            removed_set = set(removed)
            removed_ids = [
                rowid
                for rowid, path in zip(self._rowids, self._phone_paths)
                if path in removed_set
            ]
            self._db.delete_by_ids(removed_ids)
            self._index.remove(removed_ids)
            self._index.save()
            for path in removed:
                self._cache.invalidate(path)
            _logger.info("Deletion complete: %d/%d removed", len(removed), len(self._phone_paths))
            self.signals.finished.emit(removed)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Deletion failed")
            self.signals.error.emit(str(exc))
