"""Hashing helpers used for exact-duplicate detection."""

from __future__ import annotations

import hashlib


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of a byte buffer."""
    return hashlib.sha256(data).hexdigest()
