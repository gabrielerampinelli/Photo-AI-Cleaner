"""Worker that loads the (potentially heavy) AI encoder off the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from ..ai.encoder import ImageEncoder
from ..ai.factory import create_encoder
from ..models.data_models import AppConfig
from ..utils.logging_config import get_logger

_logger = get_logger(__name__)


class _LoaderSignals(QObject):
    """Signals for :class:`EncoderLoader`."""

    loaded = Signal(object)  # ImageEncoder
    error = Signal(str)


class EncoderLoader(QRunnable):
    """Instantiate the configured encoder (may download weights) in background."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self.signals = _LoaderSignals()

    def run(self) -> None:  # noqa: D401 - Qt entry point
        """Load the encoder and emit it, or emit an error string."""
        try:
            _logger.info("Loading encoder in background...")
            encoder: ImageEncoder = create_encoder(self._config)
            self.signals.loaded.emit(encoder)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Failed to load encoder")
            self.signals.error.emit(str(exc))
