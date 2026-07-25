"""Composable metadata filters for search results (date and size ranges)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..models.data_models import ImageRecord
from .search_service import RecordFilter


@dataclass
class ResultFilters:
    """User-selected filters applied on top of vector similarity results."""

    date_from: Optional[int] = None  # unix epoch seconds (inclusive)
    date_to: Optional[int] = None  # unix epoch seconds (inclusive)
    min_size: Optional[int] = None  # bytes
    max_size: Optional[int] = None  # bytes

    @property
    def is_active(self) -> bool:
        """True when at least one filter constrains the results."""
        return any(
            v is not None
            for v in (self.date_from, self.date_to, self.min_size, self.max_size)
        )

    def as_predicate(self) -> Optional[RecordFilter]:
        """Return a predicate over :class:`ImageRecord`, or ``None`` if inactive."""
        if not self.is_active:
            return None

        def predicate(record: ImageRecord) -> bool:
            if self.date_from is not None and record.created_at < self.date_from:
                return False
            if self.date_to is not None and record.created_at > self.date_to:
                return False
            if self.min_size is not None and record.size < self.min_size:
                return False
            if self.max_size is not None and record.size > self.max_size:
                return False
            return True

        return predicate
