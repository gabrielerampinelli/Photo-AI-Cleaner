"""OpenCLIP backend for :class:`ImageEncoder`.

Uses the ``open_clip`` library. Model weights are downloaded once and
cached locally under the application data directory.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from PIL import Image

from ..utils.logging_config import get_logger
from ..utils.paths import model_cache_dir
from .encoder import ImageEncoder

_logger = get_logger(__name__)


class OpenClipEncoder(ImageEncoder):
    """CLIP encoder backed by the ``open_clip`` package."""

    def __init__(
        self,
        model_name: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
        device: str = "cpu",
    ) -> None:
        """Load an OpenCLIP model and its preprocessing transform."""
        import open_clip  # imported lazily so the app starts without torch loaded
        import torch

        self._torch = torch
        self._device = device if (device != "cuda" or torch.cuda.is_available()) else "cpu"
        if self._device != device:
            _logger.warning("CUDA requested but unavailable - falling back to CPU")

        _logger.info("Loading OpenCLIP %s / %s on %s", model_name, pretrained, self._device)
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            model_name,
            pretrained=pretrained,
            cache_dir=str(model_cache_dir()),
        )
        self._model.eval().to(self._device)
        # On CUDA use half precision: it roughly halves VRAM (important on a
        # 4 GB laptop GPU) and speeds up inference, with negligible impact on
        # retrieval quality. CPU stays in float32 (no fp16 speed-up there).
        self._half = self._device == "cuda"
        if self._half:
            self._model.half()
            _logger.info("Using fp16 (half precision) on CUDA")
        self._tokenizer = open_clip.get_tokenizer(model_name)
        self._name = f"open_clip:{model_name}:{pretrained}"

        with torch.no_grad():
            dummy = self._preprocess(Image.new("RGB", (16, 16))).unsqueeze(0)
            dummy = self._to_input(dummy)
            self._dim = int(self._model.encode_image(dummy).shape[-1])
        _logger.info("OpenCLIP loaded (dim=%d)", self._dim)

    def _to_input(self, tensor):
        """Move an image tensor to the model device/precision."""
        tensor = tensor.to(self._device)
        return tensor.half() if self._half else tensor

    @property
    def embedding_dim(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return self._name

    def encode_image(self, images: Sequence[Image.Image]) -> np.ndarray:
        if not images:
            return np.zeros((0, self._dim), dtype=np.float32)
        batch = self._to_input(self._torch.stack([self._preprocess(img) for img in images]))
        with self._torch.no_grad():
            features = self._model.encode_image(batch)
        return self.normalize(features.float().cpu().numpy())

    def encode_text(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        # Token ids stay integer (long); only the model weights are fp16.
        tokens = self._tokenizer(list(texts)).to(self._device)
        with self._torch.no_grad():
            features = self._model.encode_text(tokens)
        return self.normalize(features.float().cpu().numpy())
