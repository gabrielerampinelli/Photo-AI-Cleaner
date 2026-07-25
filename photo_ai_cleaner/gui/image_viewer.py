"""A full-resolution image viewer dialog with prev/next navigation.

Displays an image streamed from the phone (bytes in RAM only), scaled to fit
and rescaled on resize. The viewer holds the ordered list of search results so
the user can move to the previous/next photo with the on-screen arrows or the
Left/Right keys, without going back to the grid. Actually fetching each image
is delegated to the main window via the :attr:`photo_requested` signal.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..models.data_models import ImageRecord


class ImageViewerDialog(QDialog):
    """Modal-less viewer showing one photo at a time, with navigation."""

    #: Emitted when a (new) photo must be fetched by the main window.
    photo_requested = Signal(object)  # ImageRecord
    #: Emitted when the user presses Delete on the currently shown photo.
    delete_requested = Signal(object)  # ImageRecord

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.resize(960, 760)
        self.setSizeGripEnabled(True)

        self._records: List[ImageRecord] = []
        self._index: int = 0
        self._current_path: Optional[str] = None
        self._source: Optional[QPixmap] = None

        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self._prev_btn = QPushButton("‹")  # ‹
        self._next_btn = QPushButton("›")  # ›
        for btn in (self._prev_btn, self._next_btn):
            btn.setFixedWidth(48)
            btn.setStyleSheet("font-size: 28px; font-weight: bold;")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # Full-height side bars; fixed width, expand vertically so the row
            # (and thus the image label) fills the whole dialog height.
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._prev_btn.setToolTip("Foto precedente (←)")
        self._next_btn.setToolTip("Foto successiva (→)")
        self._prev_btn.clicked.connect(self.show_previous)
        self._next_btn.clicked.connect(self.show_next)

        self._label = QLabel("Caricamento immagine...")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(1, 1)
        # Ignored size policy: the label takes whatever space the layout gives
        # it and does NOT shrink to the pixmap. Without this the label sizes to
        # the (scaled) image and the picture ends up tiny.
        self._label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        row.addWidget(self._prev_btn)
        row.addWidget(self._label, stretch=1)
        row.addWidget(self._next_btn)
        layout.addLayout(row, stretch=1)

    # ------------------------------------------------------------------ #
    # Playlist / navigation
    # ------------------------------------------------------------------ #
    def set_playlist(self, records: List[ImageRecord], index: int) -> None:
        """Set the ordered results and show the one at ``index``."""
        self._records = list(records)
        self._index = max(0, min(index, len(self._records) - 1))
        self._show_current()

    def show_previous(self) -> None:
        """Navigate to the previous photo, if any."""
        if self._index > 0:
            self._index -= 1
            self._show_current()

    def show_next(self) -> None:
        """Navigate to the next photo, if any."""
        if self._index < len(self._records) - 1:
            self._index += 1
            self._show_current()

    def _show_current(self) -> None:
        if not self._records:
            return
        record = self._records[self._index]
        self._current_path = record.phone_path
        self._source = None
        self._label.setText("Caricamento immagine...")
        self._refresh_nav()
        self.photo_requested.emit(record)

    def _refresh_nav(self) -> None:
        """Update the title (position) and enable/disable the arrow buttons."""
        if not self._records:
            return
        record = self._records[self._index]
        total = len(self._records)
        self.setWindowTitle(f"{record.filename}  ({self._index + 1}/{total})")
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < total - 1)

    @Slot(list)
    def on_deleted(self, removed_paths: list) -> None:
        """Remove deleted photos from the playlist and advance/close.

        Called after a successful deletion. If the currently shown photo was
        deleted, the next one (or the previous, if it was the last) is shown;
        if the playlist becomes empty the viewer closes.
        """
        removed = set(removed_paths)
        if not removed:
            return
        current_removed = self._current_path in removed
        self._records = [r for r in self._records if r.phone_path not in removed]
        if not self._records:
            self.close()
            return
        if current_removed:
            self._index = min(self._index, len(self._records) - 1)
            self._show_current()
        else:
            # The shown photo survived; just re-locate it and refresh the arrows.
            self._index = next(
                (i for i, r in enumerate(self._records) if r.phone_path == self._current_path),
                min(self._index, len(self._records) - 1),
            )
            self._refresh_nav()

    # ------------------------------------------------------------------ #
    # Worker callbacks (run on the GUI thread via queued connections)
    # ------------------------------------------------------------------ #
    @Slot(str, bytes)
    def on_ready(self, phone_path: str, data: bytes) -> None:
        """Display fetched bytes, ignoring results for a stale navigation."""
        if phone_path != self._current_path:
            return  # user already moved to another photo
        self.set_image_bytes(data)

    @Slot(str)
    def on_failed(self, phone_path: str) -> None:
        """Show an error if the current photo could not be fetched."""
        if phone_path == self._current_path:
            self._label.setText("Impossibile caricare l'immagine dal telefono.")

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def set_image_bytes(self, data: bytes) -> None:
        """Decode image bytes and display them scaled to the window."""
        image = QImage.fromData(data)
        if image.isNull():
            self._label.setText("Impossibile visualizzare l'immagine.")
            return
        self._source = QPixmap.fromImage(image)
        self._update_scaled()

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
        """Arrow keys navigate; Esc closes."""
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp):
            self.show_previous()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Space):
            self.show_next()
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._records:
                self.delete_requested.emit(self._records[self._index])
        elif key == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
