"""AI image/text encoders with a swappable backend."""

from .encoder import ImageEncoder
from .factory import create_encoder

__all__ = ["ImageEncoder", "create_encoder"]
