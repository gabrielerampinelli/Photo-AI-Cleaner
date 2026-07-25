"""The application main window orchestrating all components.

Owns the shared services (ADB client, thumbnail cache, thread pool) and the
long-lived objects (encoder, database, FAISS index, search service). It wires
the widgets together and dispatches background work so the GUI never blocks.
"""

from __future__ import annotations

import csv
from typing import List, Optional

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..adb.adb_client import AdbClient
from ..ai.encoder import ImageEncoder
from ..cache.thumbnail_cache import ThumbnailCache
from ..database.db import Database
from ..models.data_models import AppConfig, ImageRecord, SearchResult
from ..search.search_service import SearchService
from ..search.vector_index import VectorIndex
from ..utils import paths
from ..utils.config import save_config
from ..utils.formatting import format_eta, human_size
from ..utils.image_utils import decode_image
from ..utils.logging_config import get_logger
from ..workers import (
    DeleteWorker,
    EncoderLoader,
    FullImageWorker,
    IndexingWorker,
    IndexProgress,
    SearchWorker,
    ThumbnailWorker,
)
from .image_viewer import ImageViewerDialog
from .results_widget import ResultsWidget
from .search_widget import SearchWidget
from .settings_dialog import SettingsDialog
from .theme import stylesheet_for

_logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """Top-level window; see module docstring for its responsibilities."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._pool = QThreadPool.globalInstance()
        self._adb = AdbClient(adb_path=config.adb_path)
        self._cache = ThumbnailCache(capacity=config.thumbnail_cache_size)
        self._database = Database(paths.database_path())

        self._encoder: Optional[ImageEncoder] = None
        self._index: Optional[VectorIndex] = None
        self._search: Optional[SearchService] = None
        self._indexer: Optional[IndexingWorker] = None
        self._viewers: List[ImageViewerDialog] = []
        # Keeps short-lived QRunnables referenced until they finish: without a
        # strong reference Python may garbage-collect the worker (and its
        # signals QObject) before run() emits, raising "Signal source has been
        # deleted".
        self._active_workers: set = set()

        self.setWindowTitle("Photo AI Cleaner")
        self.resize(1200, 820)
        self._build_ui()
        self._build_menu()
        self._install_shortcuts()
        self.apply_theme(config.theme)

        self._check_device()
        self._load_encoder()
        self._show_home()  # land on the full gallery of indexed images

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._search_widget = SearchWidget()
        self._search_widget.search_requested.connect(self._on_search_text)
        layout.addWidget(self._search_widget)

        results_header = QLabel("Risultati")
        results_header.setObjectName("header")
        layout.addWidget(results_header)

        self._results = ResultsWidget()
        self._results.thumbnail_needed.connect(self._fetch_thumbnail)
        self._results.selection_changed.connect(self._on_selection_changed)
        self._results.find_similar_requested.connect(self._on_find_similar)
        self._results.image_dropped.connect(self._on_image_dropped)
        self._results.image_activated.connect(self._on_open_image)
        layout.addWidget(self._results, stretch=1)

        # Action buttons row.
        buttons = QHBoxLayout()
        self._home_btn = QPushButton("Home")
        self._home_btn.clicked.connect(self._show_home)
        buttons.addWidget(self._home_btn)

        self._select_all_btn = QPushButton("Seleziona tutto")
        self._select_all_btn.clicked.connect(lambda: self._results.select_all(True))
        buttons.addWidget(self._select_all_btn)

        self._clear_sel_btn = QPushButton("Deseleziona")
        self._clear_sel_btn.clicked.connect(lambda: self._results.select_all(False))
        buttons.addWidget(self._clear_sel_btn)

        buttons.addStretch(1)

        self._export_btn = QPushButton("Esporta risultati")
        self._export_btn.clicked.connect(self._export_results)
        buttons.addWidget(self._export_btn)

        self._delete_btn = QPushButton("Elimina selezionate")
        self._delete_btn.setObjectName("danger")
        self._delete_btn.clicked.connect(self._on_delete_selected)
        buttons.addWidget(self._delete_btn)

        self._index_btn = QPushButton("Aggiorna indice")
        self._index_btn.setObjectName("primary")
        self._index_btn.clicked.connect(self._on_index_toggle)
        buttons.addWidget(self._index_btn)

        self._settings_btn = QPushButton("Impostazioni")
        self._settings_btn.clicked.connect(self._open_settings)
        buttons.addWidget(self._settings_btn)
        layout.addLayout(buttons)

        # Progress row (hidden until indexing starts).
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self.setCentralWidget(central)

        self._status = self.statusBar()
        self._selection_label = QLabel("0 selezionate")
        self._status.addPermanentWidget(self._selection_label)
        self._set_status("Pronto.")

    def _build_menu(self) -> None:
        menu = self.menuBar()

        tools = menu.addMenu("Strumenti")
        dup_exact = QAction("Trova duplicati (hash)", self)
        dup_exact.triggered.connect(self._find_exact_duplicates)
        tools.addAction(dup_exact)
        dup_visual = QAction("Trova duplicati visivi (embedding)", self)
        dup_visual.triggered.connect(self._find_visual_duplicates)
        tools.addAction(dup_visual)
        tools.addSeparator()
        reconnect = QAction("Ricontrolla dispositivo", self)
        reconnect.triggered.connect(self._check_device)
        tools.addAction(reconnect)

        view = menu.addMenu("Vista")
        toggle_theme = QAction("Cambia tema chiaro/scuro", self)
        toggle_theme.triggered.connect(self._toggle_theme)
        view.addAction(toggle_theme)

    def _install_shortcuts(self) -> None:
        """Register keyboard shortcuts."""
        focus = QAction(self)
        focus.setShortcut(QKeySequence("Ctrl+F"))
        focus.triggered.connect(self._search_widget.focus_input)
        self.addAction(focus)

        select_all = QAction(self)
        select_all.setShortcut(QKeySequence("Ctrl+A"))
        select_all.triggered.connect(lambda: self._results.select_all(True))
        self.addAction(select_all)

        delete = QAction(self)
        delete.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        delete.triggered.connect(self._on_delete_selected)
        self.addAction(delete)

        reindex = QAction(self)
        reindex.setShortcut(QKeySequence("F5"))
        reindex.triggered.connect(self._on_index_toggle)
        self.addAction(reindex)

        home = QAction(self)
        home.setShortcut(QKeySequence("Ctrl+H"))
        home.triggered.connect(self._show_home)
        self.addAction(home)

    # ------------------------------------------------------------------ #
    # Worker dispatch
    # ------------------------------------------------------------------ #
    def _start_retained(self, worker, *terminal_signals) -> None:
        """Start a QRunnable, keeping it alive until one of its end signals.

        Prevents the worker (and its signals object) from being garbage
        collected mid-run. ``terminal_signals`` are the signals that mark the
        job as finished (e.g. ``ready``/``failed``).
        """
        self._active_workers.add(worker)
        for signal in terminal_signals:
            signal.connect(lambda *_, w=worker: self._active_workers.discard(w))
        self._pool.start(worker)

    # ------------------------------------------------------------------ #
    # Encoder / device lifecycle
    # ------------------------------------------------------------------ #
    def _load_encoder(self) -> None:
        self._set_status("Caricamento modello AI in corso...")
        self._set_busy(True)
        loader = EncoderLoader(self._config)
        loader.signals.loaded.connect(self._on_encoder_loaded)
        loader.signals.error.connect(self._on_encoder_error)
        self._start_retained(loader, loader.signals.loaded, loader.signals.error)

    def _on_encoder_loaded(self, encoder: ImageEncoder) -> None:
        self._encoder = encoder
        self._index = VectorIndex(encoder.embedding_dim, paths.index_path())
        # If the DB has records but the index is empty, rebuild from DB.
        if self._index.size == 0 and self._database.count() > 0:
            self._rebuild_index_from_db()
        self._search = SearchService(
            encoder,
            self._index,
            self._database,
            min_score=self._config.min_score,
            max_results=self._config.max_results,
        )
        self._set_busy(False)
        self._set_status(
            f"Modello pronto: {encoder.name} | {self._database.count()} immagini indicizzate"
        )

    def _on_encoder_error(self, message: str) -> None:
        self._set_busy(False)
        self._set_status("Errore caricamento modello.")
        QMessageBox.critical(
            self,
            "Errore modello AI",
            f"Impossibile caricare il modello:\n\n{message}",
        )

    def _rebuild_index_from_db(self) -> None:
        _logger.info("Rebuilding FAISS index from database...")
        records = self._database.iter_all(with_embedding=True)
        rowids = [r.rowid for r in records if r.embedding is not None]
        import numpy as np

        vectors = np.vstack([r.embedding for r in records if r.embedding is not None])
        self._index.rebuild(rowids, vectors)
        self._index.save()

    def _check_device(self) -> None:
        info = self._adb.device_info()
        if info.is_ready:
            self._set_status(f"Telefono {info.message}")
        else:
            self._set_status(f"Dispositivo non pronto: {info.message}")
            QMessageBox.warning(self, "Connessione telefono", info.message)

    # ------------------------------------------------------------------ #
    # Home (browse all indexed images)
    # ------------------------------------------------------------------ #
    def _show_home(self) -> None:
        """Display every indexed image, newest first."""
        records = self._database.recent_records()
        self._results.set_records(records)
        if records:
            self._set_status(f"Home: {len(records)} immagini indicizzate")
        else:
            self._set_status(
                "Nessuna immagine indicizzata. Collega il telefono e premi "
                "'Aggiorna indice'."
            )

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    def _on_search_text(self, query: str) -> None:
        if not self._ensure_ready():
            return
        self._set_status(f"Ricerca: {query!r}...")
        worker = SearchWorker(
            self._search,
            query_text=query,
            record_filter=self._search_widget.current_filters().as_predicate(),
            label=f"'{query}'",
        )
        worker.signals.results.connect(self._on_search_results)
        worker.signals.error.connect(self._on_worker_error)
        self._start_retained(worker, worker.signals.results, worker.signals.error)

    def _on_find_similar(self, rowid: int) -> None:
        if not self._ensure_ready():
            return
        self._set_status("Ricerca immagini simili...")
        worker = SearchWorker(
            self._search,
            similar_to=rowid,
            record_filter=self._search_widget.current_filters().as_predicate(),
            label="simili",
        )
        worker.signals.results.connect(self._on_search_results)
        worker.signals.error.connect(self._on_worker_error)
        self._start_retained(worker, worker.signals.results, worker.signals.error)

    def _on_image_dropped(self, local_path: str) -> None:
        if not self._ensure_ready():
            return
        try:
            with open(local_path, "rb") as handle:
                image = decode_image(handle.read())
        except OSError as exc:
            QMessageBox.warning(self, "File", f"Impossibile leggere il file:\n{exc}")
            return
        if image is None:
            QMessageBox.warning(self, "File", "Il file trascinato non è un'immagine valida.")
            return
        self._set_status("Ricerca per immagine trascinata...")
        worker = SearchWorker(
            self._search,
            image=image,
            record_filter=self._search_widget.current_filters().as_predicate(),
            label="immagine",
        )
        worker.signals.results.connect(self._on_search_results)
        worker.signals.error.connect(self._on_worker_error)
        self._start_retained(worker, worker.signals.results, worker.signals.error)

    def _on_search_results(self, label: str, results: List[SearchResult]) -> None:
        self._results.set_results(results)
        if not results:
            self._set_status(
                f"Nessun risultato pertinente per {label}. "
                "Prova un altro termine o abbassa la soglia di pertinenza nelle Impostazioni."
            )
        else:
            self._set_status(f"{len(results)} risultati per {label}")

    # ------------------------------------------------------------------ #
    # Thumbnails
    # ------------------------------------------------------------------ #
    def _fetch_thumbnail(self, phone_path: str) -> None:
        worker = ThumbnailWorker(
            self._adb, self._cache, phone_path, max_side=self._config.thumbnail_max_side
        )
        worker.signals.ready.connect(self._results.set_thumbnail)
        self._start_retained(worker, worker.signals.ready, worker.signals.failed)

    # ------------------------------------------------------------------ #
    # Opening a photo at full resolution
    # ------------------------------------------------------------------ #
    def _on_open_image(self, record: ImageRecord) -> None:
        """Open a full-resolution viewer with prev/next navigation."""
        records = self._results.all_records()
        try:
            start = next(
                i for i, r in enumerate(records) if r.phone_path == record.phone_path
            )
        except StopIteration:
            records, start = [record], 0

        viewer = ImageViewerDialog(self)
        self._viewers.append(viewer)
        viewer.finished.connect(
            lambda _=0, v=viewer: self._viewers.remove(v) if v in self._viewers else None
        )
        # The viewer asks the main window to fetch each photo it navigates to.
        viewer.photo_requested.connect(
            lambda rec, v=viewer: self._load_into_viewer(v, rec)
        )
        # Delete the currently shown photo (Canc) from within the viewer.
        viewer.delete_requested.connect(
            lambda rec, v=viewer: self._delete_from_viewer(v, rec)
        )
        viewer.set_playlist(records, start)  # triggers the first fetch
        viewer.show()
        # Bring the viewer to the front: otherwise on Windows it can open behind
        # a maximised main window and appear as if "nothing happened".
        viewer.raise_()
        viewer.activateWindow()

    def _delete_from_viewer(self, viewer: ImageViewerDialog, record: ImageRecord) -> None:
        """Confirm and delete the photo currently shown in the viewer."""
        confirm = QMessageBox.question(
            viewer,
            "Conferma eliminazione",
            (
                "Eliminare questa foto dal telefono?\n\n"
                f"{record.filename}  ({human_size(record.size)})\n\n"
                "L'operazione è irreversibile."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        worker = DeleteWorker(
            self._adb,
            self._database,
            self._index,
            self._cache,
            rowids=[record.rowid],
            phone_paths=[record.phone_path],
        )
        # Both slots are bound QObject methods -> queued to the GUI thread.
        worker.signals.finished.connect(self._on_delete_finished)  # updates the grid
        worker.signals.finished.connect(viewer.on_deleted)  # advances/closes the viewer
        worker.signals.error.connect(self._on_worker_error)
        self._set_busy(True)
        self._start_retained(worker, worker.signals.finished, worker.signals.error)

    def _load_into_viewer(self, viewer: ImageViewerDialog, record: ImageRecord) -> None:
        """Stream a photo and feed it to the viewer (GUI-thread slots)."""
        self._set_status(f"Apertura {record.filename}...")
        worker = FullImageWorker(self._adb, record.phone_path)
        # Connect to the viewer's bound slots (not lambdas): a cross-thread
        # signal to a QObject method uses a queued connection, so the QPixmap
        # work runs on the GUI thread. The viewer ignores results for a photo
        # the user has already navigated away from.
        worker.signals.ready.connect(viewer.on_ready)
        worker.signals.failed.connect(viewer.on_failed)
        self._start_retained(worker, worker.signals.ready, worker.signals.failed)

    # ------------------------------------------------------------------ #
    # Selection / deletion
    # ------------------------------------------------------------------ #
    def _on_selection_changed(self, count: int, total_bytes: int) -> None:
        if count == 0:
            self._selection_label.setText("0 selezionate")
        else:
            self._selection_label.setText(f"{count} selezionate ({human_size(total_bytes)})")

    def _on_delete_selected(self) -> None:
        records = self._results.checked_records()
        if not records:
            self._set_status("Nessuna immagine selezionata.")
            return
        total = sum(r.size for r in records)
        confirm = QMessageBox.question(
            self,
            "Conferma eliminazione",
            (
                f"Stai per eliminare {len(records)} immagini dal telefono.\n"
                f"Spazio totale: {human_size(total)}.\n\n"
                "L'operazione è irreversibile. Continuare?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True)
        self._set_status(f"Eliminazione di {len(records)} immagini...")
        worker = DeleteWorker(
            self._adb,
            self._database,
            self._index,
            self._cache,
            rowids=[r.rowid for r in records],
            phone_paths=[r.phone_path for r in records],
        )
        worker.signals.finished.connect(self._on_delete_finished)
        worker.signals.error.connect(self._on_worker_error)
        self._start_retained(worker, worker.signals.finished, worker.signals.error)

    def _on_delete_finished(self, removed_paths: List[str]) -> None:
        self._set_busy(False)
        self._results.remove_paths(removed_paths)
        self._set_status(f"Eliminate {len(removed_paths)} immagini.")

    # ------------------------------------------------------------------ #
    # Indexing
    # ------------------------------------------------------------------ #
    def _on_index_toggle(self) -> None:
        if self._indexer is not None:
            self._indexer.cancel()
            self._set_status("Annullamento indicizzazione...")
            return
        if not self._ensure_ready():
            return
        info = self._adb.device_info()
        if not info.is_ready:
            QMessageBox.warning(self, "Telefono", info.message)
            return

        self._indexer = IndexingWorker(
            self._adb,
            self._encoder,
            self._database,
            self._index,
            folders=self._config.folders,
            batch_size=self._config.batch_size,
            max_fetch_workers=self._config.max_index_workers,
        )
        self._indexer.signals.progress.connect(self._on_index_progress)
        self._indexer.signals.finished.connect(self._on_index_finished)
        self._indexer.signals.cancelled.connect(self._on_index_cancelled)
        self._indexer.signals.error.connect(self._on_index_error)

        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._index_btn.setText("Annulla indicizzazione")
        self._set_status("Indicizzazione avviata...")
        self._pool.start(self._indexer)

    def _on_index_progress(self, progress: IndexProgress) -> None:
        self._progress.setValue(progress.percent)
        self._progress.setFormat(
            f"{progress.processed}/{progress.total} "
            f"(+{progress.added}, {progress.failed} falliti) "
            f"- ETA {format_eta(progress.eta_seconds)}"
        )
        self._set_status(f"Indicizzo: {progress.current_file}")

    def _on_index_finished(self, progress: IndexProgress) -> None:
        self._reset_index_ui()
        self._set_status(
            f"Indicizzazione completata: +{progress.added} nuove, "
            f"{progress.failed} fallite, {progress.skipped} già presenti. "
            f"Totale {self._database.count()} immagini."
        )

    def _on_index_cancelled(self) -> None:
        self._reset_index_ui()
        self._set_status("Indicizzazione annullata.")

    def _on_index_error(self, message: str) -> None:
        self._reset_index_ui()
        QMessageBox.critical(self, "Errore indicizzazione", message)
        self._set_status("Errore durante l'indicizzazione.")

    def _reset_index_ui(self) -> None:
        self._indexer = None
        self._progress.setVisible(False)
        self._index_btn.setText("Aggiorna indice")

    # ------------------------------------------------------------------ #
    # Duplicates
    # ------------------------------------------------------------------ #
    def _find_exact_duplicates(self) -> None:
        if not self._ensure_ready():
            return
        groups = self._search.find_exact_duplicates()
        self._show_duplicate_groups(groups, "esatti (hash)")

    def _find_visual_duplicates(self) -> None:
        if not self._ensure_ready():
            return
        self._set_status("Analisi duplicati visivi...")
        groups = self._search.find_visual_duplicates()
        self._show_duplicate_groups(groups, "visivi (embedding)")

    def _show_duplicate_groups(self, groups, label: str) -> None:
        results: List[SearchResult] = []
        for group in groups:
            for record in group.records:
                results.append(SearchResult(record=record, score=1.0))
        self._results.set_results(results)
        self._set_status(
            f"Trovati {len(groups)} gruppi di duplicati {label} "
            f"({len(results)} immagini)."
        )

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def _export_results(self) -> None:
        records = self._results.all_records()
        if not records:
            self._set_status("Nessun risultato da esportare.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta risultati", "risultati.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    ["phone_path", "filename", "sha256", "width", "height", "size", "created_at"]
                )
                for record in records:
                    writer.writerow(
                        [
                            record.phone_path,
                            record.filename,
                            record.sha256,
                            record.width,
                            record.height,
                            record.size,
                            record.created_at,
                        ]
                    )
            self._set_status(f"Esportati {len(records)} risultati in {path}")
        except OSError as exc:
            QMessageBox.warning(self, "Esportazione", f"Errore di scrittura:\n{exc}")

    # ------------------------------------------------------------------ #
    # Settings / theme
    # ------------------------------------------------------------------ #
    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._config, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        new_config = dialog.result_config()
        model_changed = (
            new_config.model_backend != self._config.model_backend
            or new_config.model_name != self._config.model_name
            or new_config.model_pretrained != self._config.model_pretrained
            or new_config.device != self._config.device
        )
        self._config = new_config
        self._adb = AdbClient(adb_path=new_config.adb_path)
        self._cache = ThumbnailCache(capacity=new_config.thumbnail_cache_size)
        save_config(self._config, paths.default_config_path())
        self.apply_theme(new_config.theme)
        if self._search is not None:
            self._search.min_score = new_config.min_score
            self._search.max_results = new_config.max_results

        if model_changed:
            QMessageBox.information(
                self,
                "Modello cambiato",
                "Il modello è cambiato. Verrà ricaricato e potrebbe essere "
                "necessario ricostruire l'indice.",
            )
            self._load_encoder()
        self._set_status("Impostazioni salvate.")

    def _toggle_theme(self) -> None:
        new_theme = "light" if self._config.theme == "dark" else "dark"
        self._config.theme = new_theme
        self.apply_theme(new_theme)
        save_config(self._config, paths.default_config_path())

    def apply_theme(self, theme: str) -> None:
        """Apply the given theme name to the whole application."""
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet_for(theme))

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _ensure_ready(self) -> bool:
        if self._search is None or self._encoder is None:
            self._set_status("Modello non ancora pronto, attendere...")
            return False
        return True

    def _on_worker_error(self, message: str) -> None:
        self._set_busy(False)
        self._set_status("Errore.")
        QMessageBox.warning(self, "Errore", message)

    def _set_status(self, text: str) -> None:
        self._status.showMessage(text)
        _logger.debug("Status: %s", text)

    def _set_busy(self, busy: bool) -> None:
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Persist the index and close resources on shutdown."""
        try:
            if self._indexer is not None:
                self._indexer.cancel()
            if self._index is not None:
                self._index.save()
            self._database.close()
        finally:
            super().closeEvent(event)
