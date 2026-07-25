"""The search bar with query input and optional date/size filters."""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..search.filters import ResultFilters


class SearchWidget(QWidget):
    """Search input area emitting :attr:`search_requested` with the query."""

    search_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("Ricerca")
        header.setObjectName("header")
        layout.addWidget(header)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "Cerca: pizza, gatto, tramonto, selfie, meme, documento, ricevuta..."
        )
        self._input.setClearButtonEnabled(True)
        self._input.returnPressed.connect(self._emit_search)
        row.addWidget(self._input, stretch=1)

        self._search_btn = QPushButton("Cerca")
        self._search_btn.setObjectName("primary")
        self._search_btn.clicked.connect(self._emit_search)
        row.addWidget(self._search_btn)

        self._filter_toggle = QPushButton("Filtri")
        self._filter_toggle.setCheckable(True)
        self._filter_toggle.toggled.connect(self._on_toggle_filters)
        row.addWidget(self._filter_toggle)
        layout.addLayout(row)

        self._filters_panel = self._build_filters_panel()
        self._filters_panel.setVisible(False)
        layout.addWidget(self._filters_panel)

    def _build_filters_panel(self) -> QWidget:
        panel = QWidget()
        grid = QGridLayout(panel)
        grid.setContentsMargins(0, 6, 0, 6)

        self._use_date = QCheckBox("Filtra per data")
        grid.addWidget(self._use_date, 0, 0)
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        self._date_from.setDate(datetime.now().date().replace(month=1, day=1))
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("dd/MM/yyyy")
        self._date_to.setDate(datetime.now().date())
        grid.addWidget(QLabel("Da:"), 0, 1)
        grid.addWidget(self._date_from, 0, 2)
        grid.addWidget(QLabel("A:"), 0, 3)
        grid.addWidget(self._date_to, 0, 4)

        self._use_size = QCheckBox("Filtra per dimensione (KB)")
        grid.addWidget(self._use_size, 1, 0)
        self._min_size = QSpinBox()
        self._min_size.setRange(0, 1_000_000)
        self._min_size.setSuffix(" KB")
        self._max_size = QSpinBox()
        self._max_size.setRange(0, 1_000_000)
        self._max_size.setValue(1_000_000)
        self._max_size.setSuffix(" KB")
        grid.addWidget(QLabel("Min:"), 1, 1)
        grid.addWidget(self._min_size, 1, 2)
        grid.addWidget(QLabel("Max:"), 1, 3)
        grid.addWidget(self._max_size, 1, 4)
        return panel

    def _on_toggle_filters(self, checked: bool) -> None:
        self._filters_panel.setVisible(checked)

    def _emit_search(self) -> None:
        text = self._input.text().strip()
        if text:
            self.search_requested.emit(text)

    def focus_input(self) -> None:
        """Give keyboard focus to the search box (used by shortcut)."""
        self._input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._input.selectAll()

    def current_filters(self) -> ResultFilters:
        """Return the currently configured :class:`ResultFilters`."""
        filters = ResultFilters()
        if self._use_date.isChecked():
            start = datetime.combine(self._date_from.date().toPython(), time.min)
            end = datetime.combine(self._date_to.date().toPython(), time.max)
            filters.date_from = int(start.timestamp())
            filters.date_to = int(end.timestamp())
        if self._use_size.isChecked():
            filters.min_size = self._min_size.value() * 1024
            filters.max_size = self._max_size.value() * 1024
        return filters
