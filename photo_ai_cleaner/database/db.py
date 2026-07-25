"""SQLite database access for indexed images.

Stores one row per image with its embedding (as a float32 BLOB). No
thumbnails and no image copies are ever stored - only metadata and the
compact embedding vector, matching the "index, don't copy" design.

The class is thread-aware: SQLite connections are created per-thread and
writes are serialised with a lock so multiple indexing workers can persist
results safely.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ..models.data_models import ImageRecord
from ..utils.logging_config import get_logger

_logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_path  TEXT NOT NULL UNIQUE,
    filename    TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    embedding   BLOB NOT NULL,
    width       INTEGER NOT NULL,
    height      INTEGER NOT NULL,
    size        INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_images_sha256 ON images(sha256);
CREATE INDEX IF NOT EXISTS idx_images_created ON images(created_at);
CREATE INDEX IF NOT EXISTS idx_images_path ON images(phone_path);
"""


class Database:
    """Thread-safe SQLite wrapper for the ``images`` table."""

    def __init__(self, path: Path) -> None:
        """Open (and create if needed) the database at ``path``."""
        self._path = path
        self._write_lock = threading.Lock()
        self._local = threading.local()
        self._initialise()
        _logger.info("Database ready at %s", path)

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            self._local.conn = conn
        return conn

    def _initialise(self) -> None:
        conn = self._connect()
        with self._write_lock:
            conn.executescript(_SCHEMA)
            conn.commit()

    def close(self) -> None:
        """Close the calling thread's connection."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ------------------------------------------------------------------ #
    # Serialisation helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _embedding_to_blob(embedding: np.ndarray) -> bytes:
        return np.asarray(embedding, dtype=np.float32).tobytes()

    @staticmethod
    def _blob_to_embedding(blob: bytes) -> np.ndarray:
        return np.frombuffer(blob, dtype=np.float32)

    def _row_to_record(self, row: sqlite3.Row, with_embedding: bool = True) -> ImageRecord:
        return ImageRecord(
            rowid=row["id"],
            phone_path=row["phone_path"],
            filename=row["filename"],
            sha256=row["sha256"],
            width=row["width"],
            height=row["height"],
            size=row["size"],
            created_at=row["created_at"],
            last_seen=row["last_seen"],
            embedding=self._blob_to_embedding(row["embedding"]) if with_embedding else None,
        )

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def upsert_image(self, record: ImageRecord) -> int:
        """Insert or update an image row keyed by ``phone_path``.

        Returns the row id of the affected record.
        """
        if record.embedding is None:
            raise ValueError("Cannot persist a record without an embedding")
        blob = self._embedding_to_blob(record.embedding)
        conn = self._connect()
        with self._write_lock:
            cur = conn.execute(
                """
                INSERT INTO images
                    (phone_path, filename, sha256, embedding, width, height,
                     size, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(phone_path) DO UPDATE SET
                    filename=excluded.filename,
                    sha256=excluded.sha256,
                    embedding=excluded.embedding,
                    width=excluded.width,
                    height=excluded.height,
                    size=excluded.size,
                    last_seen=excluded.last_seen
                RETURNING id
                """,
                (
                    record.phone_path,
                    record.filename,
                    record.sha256,
                    blob,
                    record.width,
                    record.height,
                    record.size,
                    record.created_at,
                    record.last_seen,
                ),
            )
            # RETURNING (SQLite >= 3.35, bundled with Python 3.12) yields the
            # row id for both the insert and the conflict-update path.
            rowid = cur.fetchone()["id"]
            conn.commit()
        record.rowid = rowid
        return rowid

    def delete_by_ids(self, rowids: List[int]) -> None:
        """Delete rows by their primary keys."""
        if not rowids:
            return
        conn = self._connect()
        with self._write_lock:
            conn.executemany("DELETE FROM images WHERE id=?", [(r,) for r in rowids])
            conn.commit()
        _logger.info("Deleted %d rows from database", len(rowids))

    def delete_by_paths(self, paths: List[str]) -> None:
        """Delete rows by their phone paths."""
        if not paths:
            return
        conn = self._connect()
        with self._write_lock:
            conn.executemany("DELETE FROM images WHERE phone_path=?", [(p,) for p in paths])
            conn.commit()

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get_existing_paths(self) -> Dict[str, int]:
        """Return a mapping of ``phone_path -> stored file mtime`` for skipping.

        ``created_at`` holds the file's modification time captured at index
        time, so comparing it against the current file mtime lets the indexer
        skip files that are already indexed and unchanged. (Using ``last_seen``
        here would never match, forcing a full re-index every run.)
        """
        conn = self._connect()
        rows = conn.execute("SELECT phone_path, created_at FROM images").fetchall()
        return {row["phone_path"]: row["created_at"] for row in rows}

    def count(self) -> int:
        """Return the number of indexed images."""
        conn = self._connect()
        return conn.execute("SELECT COUNT(*) AS c FROM images").fetchone()["c"]

    def get_by_id(self, rowid: int, with_embedding: bool = True) -> Optional[ImageRecord]:
        """Return a single record by id, or ``None``."""
        conn = self._connect()
        row = conn.execute("SELECT * FROM images WHERE id=?", (rowid,)).fetchone()
        return self._row_to_record(row, with_embedding) if row else None

    def get_many(self, rowids: List[int], with_embedding: bool = False) -> List[ImageRecord]:
        """Return records for the given ids, preserving the requested order."""
        if not rowids:
            return []
        conn = self._connect()
        placeholders = ",".join("?" for _ in rowids)
        rows = conn.execute(
            f"SELECT * FROM images WHERE id IN ({placeholders})", rowids
        ).fetchall()
        by_id = {row["id"]: self._row_to_record(row, with_embedding) for row in rows}
        return [by_id[r] for r in rowids if r in by_id]

    def iter_all(self, with_embedding: bool = True) -> List[ImageRecord]:
        """Return all records (used to rebuild the FAISS index)."""
        conn = self._connect()
        rows = conn.execute("SELECT * FROM images ORDER BY id").fetchall()
        return [self._row_to_record(row, with_embedding) for row in rows]

    def find_exact_duplicates(self) -> Dict[str, List[ImageRecord]]:
        """Group records that share the same SHA-256 (exact duplicates)."""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT * FROM images
            WHERE sha256 IN (
                SELECT sha256 FROM images GROUP BY sha256 HAVING COUNT(*) > 1
            )
            ORDER BY sha256, id
            """
        ).fetchall()
        groups: Dict[str, List[ImageRecord]] = {}
        for row in rows:
            record = self._row_to_record(row, with_embedding=False)
            groups.setdefault(row["sha256"], []).append(record)
        return groups
