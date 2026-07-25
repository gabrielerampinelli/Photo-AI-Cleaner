# Usage

## 1. Connect and index

1. Connect your phone via USB and make sure it is **authorized** (see
   [INSTALLATION.md](INSTALLATION.md) → ADB setup). The status bar shows the
   connection state.
2. Click **Update index** (or press `F5`). The app:
   - lists image files in the configured folders (skipping hidden folders like
     Android's `.thumbnails`),
   - streams each image, resizes it, computes an AI embedding, and stores it,
   - shows a **progress bar** with counts and an **estimated time remaining**.
3. You can **cancel** at any time (the button becomes *Cancel indexing*).
   Indexing is **incremental**: already‑indexed, unchanged files are skipped on
   the next run, so re‑indexing to pick up new photos is fast.

> **Where are my photos?** On Android, `/sdcard` **is the internal storage**
> (it's a link to `/storage/emulated/0`, not the SD card). By default the app
> indexes `DCIM`, `Pictures`, `Download`, and `Android/media` (where WhatsApp,
> Telegram, etc. store received media). You can add more folders in
> **Settings**.

---

## 2. Search

Type a natural‑language query and press **Search** (or `Enter`):

```
pizza · cat · sunset · selfie · meme · document · receipt · screenshot · beach · dog …
```

- Results are ranked by visual similarity and shown as a thumbnail grid, each
  with a match percentage.
- The number of results is driven by the **relevance threshold** (see below),
  not a fixed cap — a broad query like "motorcycle" can return hundreds of hits.
- If nothing is relevant (e.g. you have no pizza photos), you get *"No relevant
  results"* instead of random images.

### Relevance threshold

CLIP always has a "nearest" image even when nothing truly matches. The
**relevance threshold** (Settings → *Relevance threshold*, default `0.20`) hides
results below that similarity:

- **Higher** (e.g. `0.25`) → fewer, more precise results.
- **Lower** (e.g. `0.15`) → more results, some less relevant.

`Max results` (Settings) caps how many results are displayed (default `500`).

---

## 3. Open a photo

- **Double‑click** a thumbnail (or select it and press `Enter`, or right‑click →
  **Open**) to view it **full resolution** in a resizable window. The image is
  streamed to RAM only. Press `Esc` to close.

---

## 4. Select photos

An image counts as **selected** when **either**:

- its **checkbox** is ticked, **or**
- it is **highlighted** (the light‑blue frame from a single click, `Ctrl+click`,
  or `Shift+click`).

The status bar shows the number selected and their total size. Use **Select
all** / **Deselect** for bulk changes.

---

## 5. Delete photos from the phone

1. Select the photos you want to remove.
2. Click **Delete selected** (or press `Delete`).
3. A confirmation shows the **number of images** and the **total size**. Deletion
   is **irreversible**.
4. On confirm, the files are removed on the phone (`adb shell rm`) and purged
   from the database, the FAISS index, and the thumbnail cache.

---

## 6. Extra tools

- **Find similar** — right‑click a result → *Find similar images*. Ranks the
  library by visual similarity to that photo.
- **Drag & drop** — drag an image file from your PC onto the results area to
  reverse‑search for the most similar phone photos.
- **Duplicates** — menu *Tools*:
  - *Find duplicates (hash)* — byte‑identical images (SHA‑256).
  - *Find visual duplicates (embedding)* — near‑identical images by embedding.
- **Filters** — click *Filters* to constrain results by **date** and **size**.
- **Export results** — save the current results to a **CSV** file.
- **Theme** — menu *View* → toggle light/dark.

---

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+F` | Focus the search box |
| `Enter`  | Search (in the box) / open the selected photo (in the grid) |
| `Ctrl+A` | Select all results |
| `Delete` | Delete selected photos |
| `F5`     | Update / cancel index |
| `Esc`    | Close the photo viewer |
