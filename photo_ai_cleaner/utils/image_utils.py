"""Image decoding and resizing helpers used by the indexing pipeline."""

from __future__ import annotations

import io
from typing import Optional

from PIL import Image, ImageOps

from .logging_config import get_logger

_logger = get_logger(__name__)


def decode_image(data: bytes) -> Optional[Image.Image]:
    """Decode raw image bytes into a normalised RGB :class:`PIL.Image`.

    EXIF orientation is applied so thumbnails and embeddings match what the
    user sees on the phone. Returns ``None`` if the bytes cannot be decoded.
    """
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
        return image.convert("RGB")
    except Exception as exc:  # noqa: BLE001 - decoding must never crash indexing
        _logger.warning("Failed to decode image (%d bytes): %s", len(data), exc)
        return None


def resize_for_model(image: Image.Image, size: int) -> Image.Image:
    """Return a square-ish resized copy suitable for the AI encoder."""
    return image.resize((size, size), Image.Resampling.BICUBIC)


def make_thumbnail(data: bytes, max_side: int) -> Optional[bytes]:
    """Decode image bytes and return JPEG thumbnail bytes.

    The thumbnail keeps the aspect ratio with the longest side bounded by
    ``max_side``. Returns ``None`` when decoding fails.
    """
    image = decode_image(data)
    if image is None:
        return None
    image.thumbnail((max_side, max_side), Image.Resampling.BICUBIC)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()
