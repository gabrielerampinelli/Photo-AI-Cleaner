"""Factory that builds the configured :class:`ImageEncoder` backend.

Selecting the backend from configuration keeps the concrete model class out
of the rest of the codebase - only this factory knows the mapping.
"""

from __future__ import annotations

from ..models.data_models import AppConfig
from ..utils.logging_config import get_logger
from .encoder import ImageEncoder

_logger = get_logger(__name__)


def create_encoder(config: AppConfig) -> ImageEncoder:
    """Instantiate the encoder selected in ``config.model_backend``.

    Supported backends: ``open_clip`` and ``siglip``.

    Raises:
        ValueError: If the backend name is not recognised.
    """
    backend = config.model_backend.lower()
    _logger.info("Creating encoder backend=%s device=%s", backend, config.device)

    if backend in ("open_clip", "openclip", "clip"):
        from .open_clip_encoder import OpenClipEncoder

        return OpenClipEncoder(
            model_name=config.model_name,
            pretrained=config.model_pretrained,
            device=config.device,
        )
    if backend == "siglip":
        from .siglip_encoder import SiglipEncoder

        return SiglipEncoder(model_name=config.model_name, device=config.device)

    raise ValueError(f"Unknown model backend: {config.model_backend!r}")
