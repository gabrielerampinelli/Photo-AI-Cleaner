"""FAISS-backed vector index mapping embeddings to database row ids.

Uses an inner-product flat index wrapped in an ``IndexIDMap`` so the FAISS
id equals the SQLite primary key. Because embeddings are L2-normalised by
the encoder, inner product is equivalent to cosine similarity.

The index is kept in memory and persisted to disk so it does not need to be
rebuilt from the database on every launch.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import List, Tuple

import faiss
import numpy as np

from ..utils.logging_config import get_logger

_logger = get_logger(__name__)


class VectorIndex:
    """Thread-safe wrapper around a FAISS ``IndexIDMap`` over inner product."""

    def __init__(self, dim: int, path: Path) -> None:
        """Create or load an index of dimensionality ``dim`` stored at ``path``."""
        self._dim = dim
        self._path = path
        self._lock = threading.Lock()
        self._index = self._load_or_create()

    def _load_or_create(self) -> "faiss.Index":
        if self._path.exists():
            try:
                index = faiss.read_index(str(self._path))
                if index.d == self._dim:
                    _logger.info("Loaded FAISS index (%d vectors)", index.ntotal)
                    return index
                _logger.warning(
                    "Index dim mismatch (%d != %d) - rebuilding", index.d, self._dim
                )
            except Exception as exc:  # noqa: BLE001
                _logger.error("Failed to load FAISS index: %s - rebuilding", exc)
        base = faiss.IndexFlatIP(self._dim)
        return faiss.IndexIDMap2(base)

    @property
    def size(self) -> int:
        """Number of vectors currently indexed."""
        return int(self._index.ntotal)

    @property
    def dim(self) -> int:
        """Embedding dimensionality."""
        return self._dim

    def add(self, rowid: int, embedding: np.ndarray) -> None:
        """Add or replace a single vector keyed by ``rowid``."""
        self.add_many([rowid], embedding.reshape(1, -1))

    def add_many(self, rowids: List[int], embeddings: np.ndarray) -> None:
        """Add or replace multiple vectors.

        Existing ids are removed first so re-indexing overwrites cleanly.
        """
        if not rowids:
            return
        ids = np.asarray(rowids, dtype=np.int64)
        vectors = np.ascontiguousarray(embeddings, dtype=np.float32)
        with self._lock:
            try:
                self._index.remove_ids(ids)
            except Exception:  # noqa: BLE001 - ids may simply not exist yet
                pass
            self._index.add_with_ids(vectors, ids)

    def remove(self, rowids: List[int]) -> None:
        """Remove vectors by their ids."""
        if not rowids:
            return
        with self._lock:
            self._index.remove_ids(np.asarray(rowids, dtype=np.int64))

    def search(self, query: np.ndarray, top_k: int) -> List[Tuple[int, float]]:
        """Return the ``top_k`` ``(rowid, score)`` pairs for a query vector."""
        if self.size == 0:
            return []
        vector = np.ascontiguousarray(query.reshape(1, -1), dtype=np.float32)
        with self._lock:
            scores, ids = self._index.search(vector, min(top_k, self.size))
        results: List[Tuple[int, float]] = []
        for rowid, score in zip(ids[0], scores[0]):
            if rowid != -1:
                results.append((int(rowid), float(score)))
        return results

    def rebuild(self, rowids: List[int], embeddings: np.ndarray) -> None:
        """Replace the whole index with the provided vectors."""
        base = faiss.IndexFlatIP(self._dim)
        new_index = faiss.IndexIDMap2(base)
        if rowids:
            new_index.add_with_ids(
                np.ascontiguousarray(embeddings, dtype=np.float32),
                np.asarray(rowids, dtype=np.int64),
            )
        with self._lock:
            self._index = new_index
        _logger.info("Rebuilt FAISS index with %d vectors", len(rowids))

    def save(self) -> None:
        """Persist the index to disk."""
        with self._lock:
            faiss.write_index(self._index, str(self._path))
        _logger.debug("Saved FAISS index (%d vectors)", self.size)
