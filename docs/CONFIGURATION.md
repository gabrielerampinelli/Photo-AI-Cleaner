# Configuration

Configuration is stored as JSON. The **active** config used at runtime lives at:

```
%LOCALAPPDATA%\PhotoAICleaner\config.json
```

It is created automatically on first launch (from defaults) and updated when you
change **Settings** in the app. The `config.json` in the project root is a
template/reference. Editing settings in‑app is the recommended way to change
them; if you edit the file by hand, use **UTF‑8 without BOM** (the loader
tolerates a BOM, but plain UTF‑8 is cleanest).

---

## Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model_backend` | string | `open_clip` | AI backend: `open_clip` or `siglip`. |
| `model_name` | string | `ViT-B-32` | Model architecture (see below). |
| `model_pretrained` | string | `laion2b_s34b_b79k` | Pretrained weights tag (OpenCLIP only). |
| `device` | string | `cpu` | `cpu` or `cuda`. On `cuda` the encoder uses fp16 automatically. |
| `folders` | string[] | DCIM, Pictures, Download, Android/media | Phone folders to index. |
| `batch_size` | int | `8` | Images per AI batch. Lower it if you hit GPU out‑of‑memory. |
| `min_score` | float | `0.20` | Relevance threshold — text results below this cosine similarity are hidden. |
| `max_results` | int | `500` | Maximum number of search results displayed. |
| `thumbnail_cache_size` | int | `512` | Number of thumbnails kept in the RAM LRU cache. |
| `thumbnail_max_side` | int | `256` | Longest side (px) of generated thumbnails. |
| `image_resize` | int | `224` | Reference resize size (the encoder applies its own preprocessing). |
| `max_index_workers` | int | `4` | Concurrent USB streaming workers during indexing. |
| `adb_path` | string | `adb` | Path to `adb.exe` (use a full path if not on PATH). |
| `theme` | string | `dark` | `dark` or `light`. |
| `log_level` | string | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR`. |

---

## Choosing a model

The model is swappable — changing it requires **re‑indexing** (embeddings from
different models are not compatible).

### OpenCLIP (`model_backend: "open_clip"`)

| Use case | `model_name` | `model_pretrained` | Notes |
|----------|--------------|--------------------|-------|
| **Lightweight / CPU** | `ViT-B-32` | `laion2b_s34b_b79k` | 512‑dim, fast, good default on CPU. |
| **High accuracy (recommended on GPU)** | `ViT-L-14-quickgelu` | `dfn2b` | 768‑dim, much stronger retrieval; needs more compute/VRAM. |
| Alternative strong L/14 | `ViT-L-14` | `datacomp_xl_s13b_b90k` | 768‑dim, standard GELU. |

### SigLIP (`model_backend: "siglip"`)

Set `model_name` to a HuggingFace SigLIP model, e.g.
`google/siglip-base-patch16-224`. (`model_pretrained` is ignored for SigLIP.)

> After changing the model, click **Update index** and let it rebuild. The app
> detects an embedding‑dimension mismatch and rebuilds the FAISS index; existing
> rows are re‑embedded when re‑indexed.

---

## Example `config.json` (strong model on GPU)

```json
{
  "model_backend": "open_clip",
  "model_name": "ViT-L-14-quickgelu",
  "model_pretrained": "dfn2b",
  "device": "cuda",
  "folders": [
    "/sdcard/DCIM",
    "/sdcard/Pictures",
    "/sdcard/Download",
    "/sdcard/Android/media"
  ],
  "batch_size": 8,
  "min_score": 0.20,
  "max_results": 500,
  "thumbnail_cache_size": 512,
  "thumbnail_max_side": 256,
  "image_resize": 224,
  "max_index_workers": 4,
  "adb_path": "C:\\Users\\<you>\\AppData\\Local\\Android\\platform-tools\\adb.exe",
  "theme": "dark",
  "log_level": "INFO"
}
```

---

## Where data is stored

Everything lives under `%LOCALAPPDATA%\PhotoAICleaner\`:

| Path | Contents |
|------|----------|
| `config.json` | Active configuration |
| `photos.db` | SQLite database (metadata + embeddings, **no images/thumbnails**) |
| `vectors.faiss` | FAISS vector index |
| `logs/` | Rotating log files |
| `models/` | Downloaded AI model weights |

No images or thumbnails are ever written to disk.
