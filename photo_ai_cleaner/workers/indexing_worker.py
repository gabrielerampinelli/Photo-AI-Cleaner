"""Streaming indexing worker.

Implements the pipeline described in the specification, one file at a time:

    phone -> stream bytes -> decode/resize -> AI embedding -> persist -> next

Files are streamed from the phone concurrently (I/O bound) using a thread
pool, while embeddings are produced in small batches for efficiency. The
worker reports progress, estimated remaining time, and supports
cancellation. It never copies whole images to disk.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Event
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, QRunnable, Signal

from ..adb.adb_client import AdbClient
from ..ai.encoder import ImageEncoder
from ..database.db import Database
from ..models.data_models import ImageRecord, RemoteFile
from ..search.vector_index import VectorIndex
from ..utils.hashing import sha256_bytes
from ..utils.image_utils import decode_image
from ..utils.logging_config import get_logger

_logger = get_logger(__name__)


@dataclass
class IndexProgress:
    """Snapshot of indexing progress emitted to the GUI."""

    processed: int
    total: int
    current_file: str
    added: int
    skipped: int
    failed: int
    eta_seconds: float

    @property
    def percent(self) -> int:
        """Completion percentage in the 0-100 range."""
        if self.total == 0:
            return 0
        return int(self.processed * 100 / self.total)


class _IndexSignals(QObject):
    """Signals emitted by :class:`IndexingWorker` (a QObject holder)."""

    progress = Signal(object)  # IndexProgress
    finished = Signal(object)  # IndexProgress (final)
    error = Signal(str)
    cancelled = Signal()


# A decoded, ready-to-embed image bundled with its metadata.
_Prepared = Tuple[RemoteFile, "object", str, int, int]  # file, PIL image, sha, w, h


class IndexingWorker(QRunnable):
    """A cancellable :class:`QRunnable` performing streaming indexing."""

    def __init__(
        self,
        adb: AdbClient,
        encoder: ImageEncoder,
        database: Database,
        index: VectorIndex,
        folders: List[str],
        batch_size: int = 8,
        max_fetch_workers: int = 4,
    ) -> None:
        super().__init__()
        self._adb = adb
        self._encoder = encoder
        self._db = database
        self._index = index
        self._folders = folders
        self._batch_size = max(1, batch_size)
        self._max_fetch_workers = max(1, max_fetch_workers)
        self._cancel = Event()
        self.signals = _IndexSignals()

    def cancel(self) -> None:
        """Request cooperative cancellation of the running indexing job."""
        _logger.info("Indexing cancellation requested")
        self._cancel.set()

    # ------------------------------------------------------------------ #
    # QRunnable entry point
    # ------------------------------------------------------------------ #
    def run(self) -> None:  # noqa: D401 - Qt entry point
        """Execute the indexing pipeline."""
        try:
            self._run_pipeline()
        except Exception as exc:  # noqa: BLE001 - report to GUI, never crash
            _logger.exception("Indexing failed")
            self.signals.error.emit(str(exc))

    def _run_pipeline(self) -> None:
        _logger.info("Discovering files on device...")
        all_files = self._adb.list_images(self._folders)
        known = self._db.get_existing_paths()

        # Skip files already indexed and unchanged (same mtime).
        pending = [f for f in all_files if known.get(f.path) != f.mtime]
        skipped_known = len(all_files) - len(pending)
        total = len(pending)
        _logger.info("Indexing %d files (%d already up-to-date)", total, skipped_known)

        start = time.time()
        processed = 0
        added = 0
        failed = 0

        batch: List[_Prepared] = []

        with ThreadPoolExecutor(max_workers=self._max_fetch_workers) as pool:
            future_to_file = {
                pool.submit(self._fetch_and_prepare, f): f for f in pending
            }
            for future in as_completed(future_to_file):
                if self._cancel.is_set():
                    self._drain(future_to_file)
                    self.signals.cancelled.emit()
                    return

                processed += 1
                prepared = future.result()
                current = future_to_file[future].path

                if prepared is None:
                    failed += 1
                else:
                    batch.append(prepared)
                    if len(batch) >= self._batch_size:
                        added += self._flush_batch(batch)
                        batch = []

                eta = self._estimate_eta(start, processed, total)
                self.signals.progress.emit(
                    IndexProgress(
                        processed=processed,
                        total=total,
                        current_file=current,
                        added=added,
                        skipped=skipped_known,
                        failed=failed,
                        eta_seconds=eta,
                    )
                )

        # Flush the tail batch.
        if batch and not self._cancel.is_set():
            added += self._flush_batch(batch)

        self._index.save()
        elapsed = time.time() - start
        _logger.info("Indexing complete: +%d added, %d failed in %.1fs", added, failed, elapsed)
        self.signals.finished.emit(
            IndexProgress(
                processed=processed,
                total=total,
                current_file="",
                added=added,
                skipped=skipped_known,
                failed=failed,
                eta_seconds=0.0,
            )
        )

    # ------------------------------------------------------------------ #
    # Pipeline stages
    # ------------------------------------------------------------------ #
    def _fetch_and_prepare(self, file: RemoteFile) -> Optional[_Prepared]:
        """Stream one file, decode it and compute its hash (no embedding yet)."""
        if self._cancel.is_set():
            return None
        data = self._adb.read_file(file.path)
        if not data:
            return None
        image = decode_image(data)
        if image is None:
            return None
        sha = sha256_bytes(data)
        width, height = image.size
        return (file, image, sha, width, height)

    def _flush_batch(self, batch: List[_Prepared]) -> int:
        """Embed a batch of prepared images and persist them."""
        images = [item[1] for item in batch]
        embeddings = self._encoder.encode_image(images)
        now = int(time.time())
        rowids: List[int] = []
        for (file, _image, sha, width, height), embedding in zip(batch, embeddings):
            record = ImageRecord(
                phone_path=file.path,
                filename=file.filename,
                sha256=sha,
                width=width,
                height=height,
                size=file.size,
                created_at=file.mtime,
                last_seen=now,
                embedding=embedding,
            )
            rowid = self._db.upsert_image(record)
            self._index.add(rowid, embedding)
            rowids.append(rowid)
        _logger.debug("Flushed batch of %d embeddings", len(rowids))
        return len(rowids)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _estimate_eta(start: float, processed: int, total: int) -> float:
        if processed == 0:
            return 0.0
        elapsed = time.time() - start
        rate = processed / elapsed
        remaining = total - processed
        return remaining / rate if rate > 0 else 0.0

    @staticmethod
    def _drain(futures: dict) -> None:
        """Cancel any not-yet-started futures on cancellation."""
        for future in futures:
            future.cancel()
