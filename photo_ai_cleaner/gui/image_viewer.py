"""A lightweight full-resolution image viewer dialog.

Displays an image streamed from the phone (bytes in RAM only). The picture is
scaled to fit the window while preserving the aspect ratio and rescales as the
window is resized. Press Esc or close the window to dismiss it.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QImage, QKeyEvent, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget


class ImageViewerDialog(QDialog):
    """Modal-less dialog showing a single photo scaled to fit."""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 700)
        self.setSizeGripEnabled(True)

        self._source: Optional[QPixmap] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("Caricamento immagine...")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(1, 1)
        layout.addWidget(self._label)

    @Slot(str, bytes)
    def on_ready(self, _phone_path: str, data: bytes) -> None:
        """Slot for the worker's ``ready`` signal (runs in the GUI thread).

        Connecting a cross-thread signal to this bound method makes Qt use a
        queued connection, so the QPixmap work happens on the GUI thread.
        """
        self.set_image_bytes(data)

    @Slot(str)
    def on_failed(self, _phone_path: str) -> None:
        """Slot for the worker's ``failed`` signal."""
        self.set_failed()

    def set_image_bytes(self, data: bytes) -> None:
        """Decode image bytes and display them scaled to the window."""
        image = QImage.fromData(data)
        if image.isNull():
            self._label.setText("Impossibile visualizzare l'immagine.")
            return
        self._source = QPixmap.fromImage(image)
        self._update_scaled()

    def set_failed(self) -> None:
        """Show an error message when the image could not be fetched."""
        self._label.setText("Impossibile caricare l'immagine dal telefono.")

    def _update_scaled(self) -> None:
        if self._source is None:
            return
        scaled = self._source.scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Rescale the image to the new window size."""
        super().resizeEvent(event)
        self._update_scaled()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        """Close the viewer when Esc is pressed."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
