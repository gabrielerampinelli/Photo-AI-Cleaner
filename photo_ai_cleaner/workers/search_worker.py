"""Worker running a search query off the GUI thread.

Text encoding on CPU can take a fraction of a second; running it in the
thread pool keeps the interface perfectly responsive.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QObject, QRunnable, Signal

from ..models.data_models import SearchResult
from ..search.search_service import RecordFilter, SearchService
from ..utils.logging_config import get_logger

_logger = get_logger(__name__)


class _SearchSignals(QObject):
    """Signals for :class:`SearchWorker`."""

    results = Signal(str, list)  # query label, list[SearchResult]
    error = Signal(str)


class SearchWorker(QRunnable):
    """Run a text or similarity search and emit the results."""

    def __init__(
        self,
        service: SearchService,
        *,
        query_text: Optional[str] = None,
        similar_to: Optional[int] = None,
        image: object = None,
        top_k: Optional[int] = None,
        record_filter: Optional[RecordFilter] = None,
        label: str = "",
    ) -> None:
        super().__init__()
        self._service = service
        self._query_text = query_text
        self._similar_to = similar_to
        self._image = image
        self._top_k = top_k
        self._filter = record_filter
        self._label = label
        self.signals = _SearchSignals()

    def run(self) -> None:  # noqa: D401 - Qt entry point
        """Execute the configured search and emit results."""
        try:
            results: List[SearchResult]
            if self._image is not None:
                results = self._service.search_by_image(
                    self._image, self._top_k or 60, self._filter
                )
            elif self._similar_to is not None:
                results = self._service.search_similar(
                    self._similar_to, self._top_k or 60, self._filter
                )
            else:
                # top_k=None lets the service decide (threshold / max_results).
                results = self._service.search_text(
                    self._query_text or "", self._top_k, self._filter
                )
            self.signals.results.emit(self._label, results)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Search failed")
            self.signals.error.emit(str(exc))
