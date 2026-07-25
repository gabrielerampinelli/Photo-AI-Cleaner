"""High level search service tying the encoder, index and database together.

Provides text search, "find similar" reverse search, duplicate detection
(exact via hash, visual via embeddings) and metadata filters (date, size).
"""

from __future__ import annotations

from typing import Callable, List, Optional

import numpy as np

from ..ai.encoder import ImageEncoder
from ..database.db import Database
from ..models.data_models import DuplicateGroup, ImageRecord, SearchResult
from ..utils.logging_config import get_logger
from .vector_index import VectorIndex

_logger = get_logger(__name__)

# Optional predicate used to filter records (by date range, size, ...).
RecordFilter = Callable[[ImageRecord], bool]

# CLIP works far better when the query is wrapped in natural-language prompt
# templates and the resulting text embeddings are averaged ("prompt
# ensembling"). This strongly favours real photographic content over text
# screenshots for a bare keyword like "pizza".
_PROMPT_TEMPLATES = (
    "a photo of a {}",
    "a photo of the {}",
    "a close-up photo of a {}",
    "a cropped photo of a {}",
    "a photo of many {}",
    "an image containing a {}",
    "{}",
)


class SearchService:
    """Coordinates vector search and duplicate analysis."""

    def __init__(
        self,
        encoder: ImageEncoder,
        index: VectorIndex,
        database: Database,
        min_score: float = 0.0,
        max_results: int = 500,
    ) -> None:
        self._encoder = encoder
        self._index = index
        self._db = database
        # Text results below this cosine similarity are considered irrelevant
        # and hidden, so an unmatched query (e.g. "pizza" with no pizza photos)
        # returns nothing instead of arbitrary nearest neighbours.
        self.min_score = min_score
        # Upper bound on how many results are returned/displayed.
        self.max_results = max_results

    # ------------------------------------------------------------------ #
    # Text / similarity search
    # ------------------------------------------------------------------ #
    def search_text(
        self,
        query: str,
        top_k: Optional[int] = None,
        record_filter: Optional[RecordFilter] = None,
    ) -> List[SearchResult]:
        """Search indexed images by a natural-language query.

        The number of results is driven by the relevance threshold, not a
        fixed cap: when ``min_score`` is set the whole index is scanned and
        every image above the threshold is returned (up to ``max_results``).
        """
        query = query.strip()
        if not query:
            return []
        limit = top_k or self.max_results
        embedding = self._encode_query(query)

        if self.min_score > 0:
            # Threshold decides the count: scan the full index, keep relevant.
            results = self._search_vector(embedding, self._index.size, record_filter, limit)
            kept = [r for r in results if r.score >= self.min_score]
            _logger.info(
                "Text search %r: %d results >= %.3f (of %d scanned)",
                query, len(kept), self.min_score, len(results),
            )
            return kept[:limit]

        results = self._search_vector(embedding, limit, record_filter, limit)
        _logger.info("Text search %r: %d results (top_k=%d)", query, len(results), limit)
        return results

    def _encode_query(self, query: str) -> np.ndarray:
        """Encode a text query using prompt ensembling.

        The query is expanded into several prompt templates; their normalised
        text embeddings are averaged and re-normalised into a single robust
        query vector.
        """
        prompts = [template.format(query) for template in _PROMPT_TEMPLATES]
        embeddings = self._encoder.encode_text(prompts)
        mean = embeddings.mean(axis=0)
        norm = np.linalg.norm(mean)
        if norm > 0:
            mean = mean / norm
        return mean.astype(np.float32)

    def search_similar(
        self,
        rowid: int,
        top_k: int = 60,
        record_filter: Optional[RecordFilter] = None,
    ) -> List[SearchResult]:
        """Find images visually similar to an already indexed image."""
        record = self._db.get_by_id(rowid, with_embedding=True)
        if record is None or record.embedding is None:
            return []
        _logger.info("Similarity search from image id=%d", rowid)
        results = self._search_vector(record.embedding, top_k + 1, record_filter, top_k + 1)
        return [r for r in results if r.record.rowid != rowid][:top_k]

    def search_by_image(
        self,
        image,
        top_k: int = 60,
        record_filter: Optional[RecordFilter] = None,
    ) -> List[SearchResult]:
        """Find images similar to an arbitrary (not yet indexed) PIL image.

        Used for the drag-and-drop "find similar to this file" feature.
        """
        _logger.info("Similarity search from a dropped image")
        embedding = self._encoder.encode_single_image(image)
        return self._search_vector(embedding, top_k, record_filter, top_k)

    def _search_vector(
        self,
        embedding: np.ndarray,
        fetch: int,
        record_filter: Optional[RecordFilter],
        limit: int,
    ) -> List[SearchResult]:
        """Search FAISS for ``fetch`` neighbours and return up to ``limit``.

        Args:
            fetch: How many nearest neighbours to pull from the index.
            record_filter: Optional metadata predicate (date/size filters).
            limit: Maximum number of results to return.
        """
        # Over-fetch when a filter is active so filtering still fills ``limit``.
        if record_filter:
            fetch = min(fetch * 4, self._index.size)
        hits = self._index.search(embedding, max(fetch, 1))
        if not hits:
            return []
        rowids = [rowid for rowid, _ in hits]
        records = {r.rowid: r for r in self._db.get_many(rowids, with_embedding=False)}
        results: List[SearchResult] = []
        for rowid, score in hits:
            record = records.get(rowid)
            if record is None:
                continue
            if record_filter and not record_filter(record):
                continue
            results.append(SearchResult(record=record, score=score))
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------ #
    # Duplicate detection
    # ------------------------------------------------------------------ #
    def find_exact_duplicates(self) -> List[DuplicateGroup]:
        """Return groups of byte-identical images (same SHA-256)."""
        groups = self._db.find_exact_duplicates()
        return [
            DuplicateGroup(key=sha, records=records, exact=True)
            for sha, records in groups.items()
        ]

    def find_visual_duplicates(self, threshold: float = 0.94) -> List[DuplicateGroup]:
        """Return groups of visually near-identical images via embeddings.

        Uses a greedy union over cosine similarity above ``threshold``.
        """
        records = self._db.iter_all(with_embedding=True)
        records = [r for r in records if r.embedding is not None]
        if len(records) < 2:
            return []

        matrix = np.vstack([r.embedding for r in records]).astype(np.float32)
        similarity = matrix @ matrix.T

        n = len(records)
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            parent[find(i)] = find(j)

        for i in range(n):
            for j in range(i + 1, n):
                if similarity[i, j] >= threshold:
                    union(i, j)

        clusters: dict[int, List[ImageRecord]] = {}
        for i in range(n):
            clusters.setdefault(find(i), []).append(records[i])

        groups = [
            DuplicateGroup(key=f"visual-{root}", records=members, exact=False)
            for root, members in clusters.items()
            if len(members) > 1
        ]
        _logger.info("Found %d visual duplicate groups (threshold=%.2f)", len(groups), threshold)
        return groups
