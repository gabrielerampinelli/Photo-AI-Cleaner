"""Abstract encoder interface.

Every AI backend must implement :class:`ImageEncoder`. The rest of the
application depends only on this interface, so the concrete model
(OpenCLIP, SigLIP, or a future backend) can be swapped without touching
the indexing, search or GUI layers.
"""

from __future__ import annotations

import abc
from typing import List, Sequence

import numpy as np
from PIL import Image


class ImageEncoder(abc.ABC):
    """Encode images and text into a shared embedding space.

    Implementations must return **L2-normalised** ``float32`` vectors so that
    an inner-product FAISS index yields cosine similarity directly.
    """

    @property
    @abc.abstractmethod
    def embedding_dim(self) -> int:
        """Dimensionality of the produced embedding vectors."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human readable identifier of the loaded model."""

    @abc.abstractmethod
    def encode_image(self, images: Sequence[Image.Image]) -> np.ndarray:
        """Encode a batch of PIL images.

        Args:
            images: Sequence of RGB PIL images.

        Returns:
            A ``(len(images), embedding_dim)`` float32 array of normalised
            embeddings.
        """

    @abc.abstractmethod
    def encode_text(self, texts: Sequence[str]) -> np.ndarray:
        """Encode a batch of text queries into the shared embedding space."""

    def encode_single_image(self, image: Image.Image) -> np.ndarray:
        """Convenience helper to encode one image, returning a 1-D vector."""
        return self.encode_image([image])[0]

    def encode_single_text(self, text: str) -> np.ndarray:
        """Convenience helper to encode one text, returning a 1-D vector."""
        return self.encode_text([text])[0]

    @staticmethod
    def normalize(vectors: np.ndarray) -> np.ndarray:
        """L2-normalise a batch of vectors (rows)."""
        vectors = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (vectors / norms).astype(np.float32)


__all__: List[str] = ["ImageEncoder"]
