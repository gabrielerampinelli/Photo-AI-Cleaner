"""Settings dialog to edit the :class:`AppConfig` (model, device, folders...)."""

from __future__ import annotations

import copy
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..models.data_models import AppConfig


class SettingsDialog(QDialog):
    """Modal dialog editing a copy of the configuration."""

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Impostazioni")
        self.setMinimumWidth(520)
        self._config = copy.deepcopy(config)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._backend = QComboBox()
        self._backend.addItems(["open_clip", "siglip"])
        self._backend.setCurrentText(self._config.model_backend)
        form.addRow("Backend modello:", self._backend)

        self._model_name = QLineEdit(self._config.model_name)
        form.addRow("Nome modello:", self._model_name)

        self._pretrained = QLineEdit(self._config.model_pretrained)
        form.addRow("Pesi (pretrained):", self._pretrained)

        self._device = QComboBox()
        self._device.addItems(["cpu", "cuda"])
        self._device.setCurrentText(self._config.device)
        form.addRow("Device:", self._device)

        self._batch = QSpinBox()
        self._batch.setRange(1, 128)
        self._batch.setValue(self._config.batch_size)
        form.addRow("Dimensione batch:", self._batch)

        self._min_score = QDoubleSpinBox()
        self._min_score.setRange(0.0, 1.0)
        self._min_score.setSingleStep(0.01)
        self._min_score.setDecimals(2)
        self._min_score.setValue(self._config.min_score)
        self._min_score.setToolTip(
            "Similarità minima per mostrare un risultato di ricerca.\n"
            "Più alta = solo risultati molto pertinenti; più bassa = più risultati."
        )
        form.addRow("Soglia di pertinenza:", self._min_score)

        self._max_results = QSpinBox()
        self._max_results.setRange(10, 100000)
        self._max_results.setValue(self._config.max_results)
        self._max_results.setToolTip("Numero massimo di risultati mostrati per una ricerca.")
        form.addRow("Risultati massimi:", self._max_results)

        self._workers = QSpinBox()
        self._workers.setRange(1, 32)
        self._workers.setValue(self._config.max_index_workers)
        form.addRow("Thread indicizzazione:", self._workers)

        self._cache = QSpinBox()
        self._cache.setRange(16, 8192)
        self._cache.setValue(self._config.thumbnail_cache_size)
        form.addRow("Cache miniature (n.):", self._cache)

        self._theme = QComboBox()
        self._theme.addItems(["dark", "light"])
        self._theme.setCurrentText(self._config.theme)
        form.addRow("Tema:", self._theme)

        self._adb_path = QLineEdit(self._config.adb_path)
        form.addRow("Percorso adb:", self._adb_path)

        layout.addLayout(form)

        layout.addWidget(QLabel("Cartelle sul telefono:"))
        self._folders = QListWidget()
        self._folders.addItems(self._config.folders)
        layout.addWidget(self._folders)

        folder_buttons = QHBoxLayout()
        add_btn = QPushButton("Aggiungi cartella")
        add_btn.clicked.connect(self._add_folder)
        remove_btn = QPushButton("Rimuovi selezionata")
        remove_btn.clicked.connect(self._remove_folder)
        folder_buttons.addWidget(add_btn)
        folder_buttons.addWidget(remove_btn)
        folder_buttons.addStretch(1)
        layout.addLayout(folder_buttons)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_folder(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Aggiungi cartella", "Percorso sul telefono:", text="/sdcard/"
        )
        if ok and text.strip():
            self._folders.addItem(text.strip())

    def _remove_folder(self) -> None:
        for item in self._folders.selectedItems():
            self._folders.takeItem(self._folders.row(item))

    def result_config(self) -> AppConfig:
        """Return a new :class:`AppConfig` reflecting the dialog's values."""
        cfg = copy.deepcopy(self._config)
        cfg.model_backend = self._backend.currentText()
        cfg.model_name = self._model_name.text().strip()
        cfg.model_pretrained = self._pretrained.text().strip()
        cfg.device = self._device.currentText()
        cfg.batch_size = self._batch.value()
        cfg.min_score = self._min_score.value()
        cfg.max_results = self._max_results.value()
        cfg.max_index_workers = self._workers.value()
        cfg.thumbnail_cache_size = self._cache.value()
        cfg.theme = self._theme.currentText()
        cfg.adb_path = self._adb_path.text().strip() or "adb"
        cfg.folders = [
            self._folders.item(i).text() for i in range(self._folders.count())
        ]
        return cfg
