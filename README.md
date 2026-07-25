# Photo AI Cleaner

**Search the photos on your Android phone with natural language — fully offline, local, no server, no Docker, no WSL.**

Photo AI Cleaner is a local desktop app (Windows, PySide6) that indexes the
photos stored on a USB‑connected Android phone and lets you search them the way
you'd search *Google Photos* ("pizza", "cat", "sunset", "selfie", "receipt",
"screenshot"…) — except everything runs on your PC. Photos are read **one at a
time in streaming**, turned into AI embeddings, and indexed locally. **No photo
is ever copied to your PC.**

---

## Features

- 🔍 **Semantic search** with OpenCLIP / SigLIP (natural‑language queries)
- 📱 **USB / ADB** phone access — streams each image, never bulk‑copies
- 🧠 **Swappable AI backend** behind an `ImageEncoder` interface (OpenCLIP or SigLIP)
- ⚡ **GPU (CUDA) support** with automatic fp16, or CPU
- 🗂️ **FAISS** vector search + **SQLite** metadata (embeddings only, no thumbnails on disk)
- 🖼️ **On‑demand thumbnails** with an in‑RAM LRU cache
- 🔎 **Find similar** images (right‑click) and **drag‑and‑drop** an image to reverse‑search
- 👯 **Duplicate detection** — exact (hash) and visual (embeddings)
- 🎚️ **Relevance threshold** so irrelevant queries return nothing instead of random photos
- 📅 **Date & size filters**, **CSV export**
- 🗑️ **Safe deletion** on the phone with a confirmation showing count + total size
- 🌗 **Light / dark theme**, keyboard shortcuts, progress bar with ETA and cancel
- 🖱️ **Double‑click to open** a photo full‑resolution; click to select (blue frame)

---

## Quick start

```powershell
# 1. Create and activate a virtual environment (Python 3.12+)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) For an NVIDIA GPU, install the CUDA build of PyTorch
#    See docs/INSTALLATION.md for details.

# 4. Make sure ADB is installed and your phone is connected + authorized
#    See docs/INSTALLATION.md → "ADB setup"

# 5. Run
python run.py
```

Then click **Update index** (or press `F5`) to index your phone, type a query,
and press **Search**.

---

## Requirements

- **Python 3.12+**
- **Windows 10/11**
- **[Android Platform Tools (adb)](https://developer.android.com/tools/releases/platform-tools)** on your `PATH` (or configured in `config.json`)
- An Android phone with **USB debugging** enabled
- *(Optional)* an **NVIDIA GPU** with recent drivers for CUDA acceleration

Full, step‑by‑step instructions are in **[docs/INSTALLATION.md](docs/INSTALLATION.md)**.

---

## Documentation

| Guide | Contents |
|-------|----------|
| **[docs/INSTALLATION.md](docs/INSTALLATION.md)** | Python, dependencies, CPU vs GPU (CUDA), ADB setup |
| **[docs/USAGE.md](docs/USAGE.md)** | Indexing, searching, opening, selecting, deleting, duplicates, filters, shortcuts |
| **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)** | Every `config.json` field, model choices, where data is stored |
| **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** | Module layout and responsibilities |
| **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** | ADB not found, unauthorized, no thumbnails, GPU not used, etc. |

---

## How it works

```
phone (USB/ADB)
   └─ stream one image's bytes  ──►  decode + resize
                                        └─ AI embedding (OpenCLIP/SigLIP)
                                             └─ store embedding (SQLite + FAISS)
                                                  └─ next photo …
```

A text query is embedded into the same vector space (with prompt ensembling)
and the nearest images are returned by cosine similarity via FAISS. Thumbnails
are pulled from the phone **only when a result needs to be shown** and cached in
RAM.

---

## Project layout

```
photo_ai_cleaner/
├── main.py            # entry point
├── gui/               # PySide6: window, search bar, results, viewer, settings, theme
├── adb/               # ADB wrapper (device detection, streaming, delete)
├── ai/                # ImageEncoder interface + OpenCLIP/SigLIP backends + factory
├── database/          # SQLite (metadata + embeddings, no thumbnails)
├── search/            # FAISS index + search service + filters
├── cache/             # in‑RAM LRU thumbnail cache
├── workers/           # QRunnable: indexing, thumbnails, delete, search, image load
├── models/            # domain dataclasses + AppConfig
└── utils/             # logging, config, hashing, image, paths, formatting
```

The AI model lives behind the abstract `ImageEncoder` (`ai/encoder.py`): to swap
backends you only change `config.json` (or add a class and register it in
`ai/factory.py`) — nothing else in the app changes.

---

## Data & privacy

Everything is stored locally under `%LOCALAPPDATA%\PhotoAICleaner\`:
`photos.db` (SQLite), `vectors.faiss` (index), `logs/`, `models/` (AI weights),
`config.json`. **No images or thumbnails are ever written to disk**, and nothing
leaves your machine except the one‑time download of the AI model weights.

---

## License

This project is provided as‑is for personal/local use. See individual
dependencies for their respective licenses.
