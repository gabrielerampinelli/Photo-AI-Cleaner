"""A thread-safe, size-bounded LRU cache holding thumbnails in RAM only.

Thumbnails are requested from the phone only when needed (e.g. to display a
search result) and cached here. Nothing is written to disk, honouring the
"do not store thumbnails or copies" requirement.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Optional


class ThumbnailCache:
    """Bounded LRU cache mapping ``phone_path -> jpeg bytes``."""

    def __init__(self, capacity: int = 512) -> None:
        """Create a cache holding at most ``capacity`` thumbnails."""
        self._capacity = max(1, capacity)
        self._store: "OrderedDict[str, bytes]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[bytes]:
        """Return cached bytes for ``key`` and mark it most-recently used."""
        with self._lock:
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            return self._store[key]

    def put(self, key: str, value: bytes) -> None:
        """Insert ``value`` for ``key``, evicting the least-recently used."""
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = value
            while len(self._store) > self._capacity:
                self._store.popitem(last=False)

    def contains(self, key: str) -> bool:
        """Return True if ``key`` is cached (without touching LRU order)."""
        with self._lock:
            return key in self._store

    def invalidate(self, key: str) -> None:
        """Remove a single entry if present."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Empty the cache."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
