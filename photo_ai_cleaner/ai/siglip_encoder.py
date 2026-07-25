"""SigLIP backend for :class:`ImageEncoder` via HuggingFace Transformers."""

from __future__ import annotations

from typing import Sequence

import numpy as np
from PIL import Image

from ..utils.logging_config import get_logger
from ..utils.paths import model_cache_dir
from .encoder import ImageEncoder

_logger = get_logger(__name__)


class SiglipEncoder(ImageEncoder):
    """Image/text encoder backed by a HuggingFace SigLIP model."""

    def __init__(
        self,
        model_name: str = "google/siglip-base-patch16-224",
        device: str = "cpu",
    ) -> None:
        """Load a SigLIP model and processor from HuggingFace."""
        import torch
        from transformers import AutoModel, AutoProcessor

        self._torch = torch
        self._device = device if (device != "cuda" or torch.cuda.is_available()) else "cpu"
        if self._device != device:
            _logger.warning("CUDA requested but unavailable - falling back to CPU")

        _logger.info("Loading SigLIP %s on %s", model_name, self._device)
        cache = str(model_cache_dir())
        self._model = AutoModel.from_pretrained(model_name, cache_dir=cache).to(self._device)
        self._processor = AutoProcessor.from_pretrained(model_name, cache_dir=cache)
        self._model.eval()
        self._name = f"siglip:{model_name}"
        self._dim = int(self._model.config.projection_dim)
        _logger.info("SigLIP loaded (dim=%d)", self._dim)

    @property
    def embedding_dim(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return self._name

    def encode_image(self, images: Sequence[Image.Image]) -> np.ndarray:
        if not images:
            return np.zeros((0, self._dim), dtype=np.float32)
        inputs = self._processor(images=list(images), return_tensors="pt").to(self._device)
        with self._torch.no_grad():
            features = self._model.get_image_features(**inputs)
        return self.normalize(features.cpu().numpy())

    def encode_text(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        inputs = self._processor(
            text=list(texts), padding="max_length", return_tensors="pt"
        ).to(self._device)
        with self._torch.no_grad():
            features = self._model.get_text_features(**inputs)
        return self.normalize(features.cpu().numpy())
