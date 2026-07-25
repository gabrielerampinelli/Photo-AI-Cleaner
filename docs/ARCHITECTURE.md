# Architecture

Photo AI Cleaner is a modular desktop app. Each package has a single
responsibility and depends on abstractions, so pieces (AI model, storage, GUI)
can change independently.

```
photo_ai_cleaner/
├── main.py            # entry point: logging, config, QApplication, MainWindow
├── gui/               # presentation (PySide6)
│   ├── main_window.py     # orchestrates services + widgets, dispatches workers
│   ├── search_widget.py   # query box + date/size filters
│   ├── results_widget.py  # thumbnail grid, selection, drag&drop, context menu
│   ├── image_viewer.py    # full-resolution viewer dialog
│   ├── settings_dialog.py # edit AppConfig
│   └── theme.py           # light/dark stylesheets
├── adb/               # the ONLY module that shells out to adb
│   └── adb_client.py      # device detection, list, stream, delete
├── ai/                # AI encoders
│   ├── encoder.py         # abstract ImageEncoder (encode_image / encode_text)
│   ├── open_clip_encoder.py
│   ├── siglip_encoder.py
│   └── factory.py         # build the configured backend
├── database/
│   └── db.py              # thread-safe SQLite (images table)
├── search/
│   ├── vector_index.py    # FAISS IndexIDMap2 over inner product (cosine)
│   ├── search_service.py  # text/similar/image search, duplicates, threshold
│   └── filters.py         # date/size result filters
├── cache/
│   └── thumbnail_cache.py # in-RAM LRU cache (no disk)
├── workers/           # QRunnable background jobs (keep the GUI responsive)
│   ├── indexing_worker.py # streaming pipeline + progress/ETA/cancel
│   ├── thumbnail_worker.py
│   ├── full_image_worker.py
│   ├── delete_worker.py
│   ├── search_worker.py
│   └── encoder_loader.py
├── models/
│   └── data_models.py     # dataclasses: AppConfig, ImageRecord, SearchResult, …
└── utils/                 # logging, config, hashing, image, paths, formatting
```

---

## Key design points

### The `ImageEncoder` abstraction

`ai/encoder.py` defines the abstract interface:

```python
class ImageEncoder(ABC):
    def encode_image(self, images) -> np.ndarray: ...
    def encode_text(self, texts) -> np.ndarray: ...
```

Implementations must return **L2‑normalised float32** vectors, so an
inner‑product FAISS index yields cosine similarity directly. `ai/factory.py`
builds the concrete backend from `config.json`; the rest of the app never
imports a concrete model class.

### Streaming indexing pipeline

`workers/indexing_worker.py` implements, one file at a time:

```
phone → stream bytes (adb exec-out cat) → decode/resize → embedding → SQLite + FAISS → next
```

Files are fetched concurrently (I/O bound) via a thread pool while embeddings are
computed in small batches. The worker reports progress and ETA and supports
cooperative cancellation. Already‑indexed, unchanged files are skipped
(comparing the stored file mtime).

### Persistence

- **SQLite** (`database/db.py`) stores one row per image: `id, phone_path,
  filename, sha256, embedding (BLOB), width, height, size, created_at,
  last_seen`. Connections are per‑thread; writes are serialised with a lock.
- **FAISS** (`search/vector_index.py`) maps the SQLite row id → embedding via
  `IndexIDMap2`, persisted to `vectors.faiss`.

### Threading model

The GUI thread never blocks. Heavy work runs on `QThreadPool` as `QRunnable`s
that emit Qt signals. Signals are connected to **bound QObject slots** (not
lambdas) so cross‑thread updates are delivered on the GUI thread via queued
connections — important for anything touching `QPixmap`.

### Search & relevance

`search/search_service.py` embeds the query with **prompt ensembling** (several
"a photo of a …" templates averaged), searches FAISS, and applies a **relevance
threshold** so unmatched queries return nothing. The number of results is driven
by the threshold up to `max_results`, not a fixed cap.
