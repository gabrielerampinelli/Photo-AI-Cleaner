# Troubleshooting

## "ADB not found"

The app can't launch `adb`.

- Install [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools)
  and either add the folder to your **PATH** or set the full path to `adb.exe`
  in `config.json` → `"adb_path"` (e.g.
  `C:\\Users\\<you>\\AppData\\Local\\Android\\platform-tools\\adb.exe`).
- Verify with `adb version`.
- If you just added it to PATH, **open a new terminal** (or restart the app) so
  the PATH change is picked up. Setting `adb_path` to the full exe path avoids
  this entirely.
- If you hand‑edited `config.json` and it seems ignored, make sure the file is
  **UTF‑8 without BOM** (a BOM used to break parsing; the loader now tolerates
  it, but plain UTF‑8 is safest).

## Device shows "unauthorized"

- Unlock the phone screen; a **"Allow USB debugging?"** dialog should appear —
  tap **Allow** (tick *"Always allow from this computer"*).
- If it doesn't appear: Developer options → **Revoke USB debugging
  authorizations**, then re‑plug the cable.
- Confirm with `adb devices` → should read `device`, not `unauthorized`.

## Device shows "offline" / not detected

- Re‑plug the USB cable; set the phone's USB mode to **File transfer (MTP)**.
- Try another cable/port (some cables are charge‑only).
- `adb kill-server` then `adb start-server`, then `adb devices`.

## "It only found 490 photos, but I have thousands"

- `/sdcard` **is** the internal storage (a link to `/storage/emulated/0`), not
  the SD card — despite the name.
- Most app photos (WhatsApp, Telegram, …) live under **`/sdcard/Android/media`**,
  which is indexed by default. If you removed it, add it back in **Settings →
  Folders**, then **Update index**.
- Hidden folders (e.g. Android's `.thumbnails` cache and `.trashed-…` files) are
  intentionally skipped — they aren't real photos.

## Images fail to decode / thumbnails don't show

- Ensure the device is **authorized** (`adb devices` → `device`).
- Confirm you can read a file:
  `adb exec-out "cat '/sdcard/DCIM/Camera/<somefile>.jpg'" > test.jpg`
  and check `test.jpg` is a valid image. If you get a text error like
  `No such file or directory`, the path/quoting is wrong.

## The photo viewer stays on "Loading image…"

- Fixed in current versions (the viewer updates on the GUI thread). If you built
  from an older checkout, update the code and restart.

## Search returns irrelevant photos (e.g. "pizza" shows non‑pizza)

- This usually means you simply **have no matching photos** — CLIP still returns
  the "nearest" images. Raise the **relevance threshold** (Settings) to hide
  weak matches; you'll get *"No relevant results"* instead of random photos.

## Search returns too few results (capped)

- Increase **Max results** in Settings (default 500). The result count is
  otherwise driven by the relevance threshold — lower it to see more.

## GPU is not being used

- Check `python -c "import torch; print(torch.cuda.is_available())"`. If `False`,
  you have the **CPU build** of PyTorch — install the CUDA build (see
  [INSTALLATION.md](INSTALLATION.md) step 4).
- Set `"device": "cuda"` in `config.json`. If CUDA is unavailable, the app logs a
  warning and falls back to CPU.

## CUDA out of memory

- Lower `batch_size` in `config.json` (e.g. `4`).
- Use a smaller model (`ViT-B-32` instead of `ViT-L-14`).
- On CUDA the encoder already uses fp16 to minimise VRAM.

## Changing the model breaks search / dimension mismatch

- Different models produce different‑dimension embeddings. After changing the
  model, **re‑index** (Update index). The FAISS index is rebuilt automatically
  when a dimension mismatch is detected.

## Where are the logs?

`%LOCALAPPDATA%\PhotoAICleaner\logs\photo_ai_cleaner.log`. Set
`"log_level": "DEBUG"` in `config.json` for more detail.
