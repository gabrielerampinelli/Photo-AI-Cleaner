"""The results grid: a thumbnail gallery with checkbox multi-selection.

Responsibilities:
* display :class:`SearchResult` items as a responsive icon grid,
* lazily request thumbnails (emitting :attr:`thumbnail_needed`),
* track checked items and report total selection size,
* offer a right-click "find similar images" action,
* accept dropped image files to run a reverse (similarity) search.

All heavy work (fetching thumbnails, encoding) happens in the main window;
this widget only deals with presentation and user interaction.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from ..models.data_models import ImageRecord, SearchResult

_ROLE_RECORD = int(Qt.ItemDataRole.UserRole) + 1
_THUMB_SIZE = 180


class _DropListWidget(QListWidget):
    """A :class:`QListWidget` that emits a signal when an image file is dropped.

    Qt dispatches drag/drop through C++ virtual methods, so these handlers must
    be overridden at the class level (not assigned onto an instance) to run.
    """

    file_dropped = Signal(str)  # local file path
    return_pressed = Signal()  # Enter/Return pressed on the current item

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.return_pressed.emit()
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.file_dropped.emit(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()


class ResultsWidget(QWidget):
    """Gallery of search results with selection and drag-and-drop."""

    thumbnail_needed = Signal(str)  # phone_path
    selection_changed = Signal(int, int)  # count, total_bytes
    find_similar_requested = Signal(int)  # rowid
    image_dropped = Signal(str)  # local file path dropped by the user
    image_activated = Signal(object)  # ImageRecord (double-clicked to open)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._items_by_path: Dict[str, QListWidgetItem] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._list = _DropListWidget()
        self._list.file_dropped.connect(self.image_dropped)
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setMovement(QListWidget.Movement.Static)
        self._list.setIconSize(QSize(_THUMB_SIZE, _THUMB_SIZE))
        self._list.setGridSize(QSize(_THUMB_SIZE + 24, _THUMB_SIZE + 48))
        self._list.setSpacing(8)
        self._list.setUniformItemSizes(True)
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.itemSelectionChanged.connect(self._emit_selection)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.return_pressed.connect(self._on_return_pressed)

        # Accept dropped image files onto the gallery (see _DropListWidget).
        self._list.setAcceptDrops(True)
        self._list.viewport().setAcceptDrops(True)

        layout.addWidget(self._list)

    # ------------------------------------------------------------------ #
    # Populating results
    # ------------------------------------------------------------------ #
    def set_results(self, results: List[SearchResult]) -> None:
        """Replace the gallery with a new list of results."""
        self._list.clear()
        self._items_by_path.clear()
        placeholder = self._placeholder_icon()
        for result in results:
            record = result.record
            item = QListWidgetItem(placeholder, self._caption(record, result.score))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(_ROLE_RECORD, record)
            item.setToolTip(record.phone_path)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self._list.addItem(item)
            self._items_by_path[record.phone_path] = item
            self.thumbnail_needed.emit(record.phone_path)
        self.selection_changed.emit(0, 0)

    def set_thumbnail(self, phone_path: str, jpeg_bytes: bytes) -> None:
        """Attach a fetched thumbnail to the matching item."""
        item = self._items_by_path.get(phone_path)
        if item is None:
            return
        image = QImage.fromData(jpeg_bytes, "JPEG")
        if not image.isNull():
            item.setIcon(QIcon(QPixmap.fromImage(image)))

    # ------------------------------------------------------------------ #
    # Selection handling
    # ------------------------------------------------------------------ #
    def _on_item_changed(self, _item: QListWidgetItem) -> None:
        self._emit_selection()

    def _emit_selection(self) -> None:
        """Recompute and broadcast the effective selection (count + size)."""
        records = self.selected_records()
        total = sum(r.size for r in records)
        self.selection_changed.emit(len(records), total)

    def selected_records(self) -> List[ImageRecord]:
        """Return the effectively selected records.

        An image counts as selected when its checkbox is ticked **or** when it
        is highlighted (the light-blue frame from a single click / Ctrl+click /
        Shift+click). The two mechanisms are merged, without duplicates.
        """
        records: List[ImageRecord] = []
        seen: set[str] = set()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked or item.isSelected():
                record: ImageRecord = item.data(_ROLE_RECORD)
                if record.phone_path not in seen:
                    seen.add(record.phone_path)
                    records.append(record)
        return records

    # Backwards-compatible alias: callers asking for "checked" records now get
    # the effective selection (checkbox or highlight).
    checked_records = selected_records

    def all_records(self) -> List[ImageRecord]:
        """Return every record currently displayed."""
        return [self._list.item(i).data(_ROLE_RECORD) for i in range(self._list.count())]

    def select_all(self, checked: bool = True) -> None:
        """Check or uncheck every item (and clear the highlight when clearing).

        "Deseleziona" must also drop the light-blue highlight selection, since
        highlighted items now count as selected.
        """
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(state)
        if not checked:
            self._list.clearSelection()

    def remove_paths(self, phone_paths: List[str]) -> None:
        """Remove items matching the given phone paths (after deletion)."""
        for path in phone_paths:
            item = self._items_by_path.pop(path, None)
            if item is not None:
                self._list.takeItem(self._list.row(item))
        self._emit_selection()

    # ------------------------------------------------------------------ #
    # Opening a photo
    # ------------------------------------------------------------------ #
    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Emit the record so the main window can open a full-size viewer."""
        record: ImageRecord = item.data(_ROLE_RECORD)
        if record is not None:
            self.image_activated.emit(record)

    def _on_return_pressed(self) -> None:
        """Open the currently selected item when Enter is pressed."""
        item = self._list.currentItem()
        if item is not None:
            self._on_item_double_clicked(item)

    # ------------------------------------------------------------------ #
    # Context menu (find similar)
    # ------------------------------------------------------------------ #
    def _on_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        record: ImageRecord = item.data(_ROLE_RECORD)
        menu = QMenu(self)
        open_action = QAction("Apri", self)
        open_action.triggered.connect(lambda: self.image_activated.emit(record))
        menu.addAction(open_action)
        similar = QAction("Trova immagini simili a questa", self)
        similar.triggered.connect(lambda: self.find_similar_requested.emit(record.rowid))
        menu.addAction(similar)
        check = QAction("Seleziona / deseleziona", self)
        check.triggered.connect(lambda: self._toggle_item(item))
        menu.addAction(check)
        menu.exec(self._list.viewport().mapToGlobal(pos))

    @staticmethod
    def _toggle_item(item: QListWidgetItem) -> None:
        new = (
            Qt.CheckState.Unchecked
            if item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        item.setCheckState(new)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _caption(record: ImageRecord, score: float) -> str:
        return f"{record.filename}\n{score * 100:.0f}%"

    @staticmethod
    def _placeholder_icon() -> QIcon:
        pix = QPixmap(_THUMB_SIZE, _THUMB_SIZE)
        pix.fill(Qt.GlobalColor.darkGray)
        return QIcon(pix)
