# Installation

This guide covers a full setup on **Windows 10/11** with **Python 3.12+**.

---

## 1. Python

Install **Python 3.12 or newer** from [python.org](https://www.python.org/downloads/).
During installation, tick **"Add Python to PATH"**.

Verify:

```powershell
python --version   # should print 3.12.x or newer
```

---

## 2. Get the code and create a virtual environment

```powershell
cd path\to\AI_photo_cleaner

python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> If activation is blocked by execution policy, run PowerShell as your user and:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

---

## 3. Install dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

This installs PySide6, Pillow, NumPy, FAISS (CPU), and the AI stack
(`open_clip_torch`, `torch`, `torchvision`, `transformers`).

By default `pip` installs the **CPU build** of PyTorch. This works everywhere but
is slower. If you have an NVIDIA GPU, continue with step 4.

---

## 4. (Optional) GPU acceleration with CUDA

An NVIDIA GPU makes indexing several times faster. You need a reasonably recent
GPU driver.

1. Check your GPU and driver:

   ```powershell
   nvidia-smi
   ```

2. Install the **CUDA build** of PyTorch that matches your setup. Pick the
   correct CUDA index URL for your driver from
   [pytorch.org](https://pytorch.org/get-started/locally/). Example that works
   for an RTX 3050 with a recent driver (CUDA 12.6):

   ```powershell
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126 --force-reinstall
   ```

   To pin exact versions (recommended, keeps `open_clip`/`torchvision` compatible):

   ```powershell
   pip install "torch==2.13.0" "torchvision==0.28.0" --index-url https://download.pytorch.org/whl/cu126 --force-reinstall
   ```

3. Verify CUDA is available:

   ```powershell
   python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
   # -> True NVIDIA GeForce RTX 3050 Laptop GPU
   ```

4. Set `"device": "cuda"` in `config.json` (see
   [CONFIGURATION.md](CONFIGURATION.md)). On CUDA the encoder automatically uses
   **fp16 (half precision)**, which halves VRAM usage — important on 4 GB laptop
   GPUs — and speeds up inference. If CUDA is requested but unavailable, the app
   falls back to CPU with a warning.

> **VRAM note:** the strong `ViT-L-14` model fits in 4 GB thanks to fp16. If you
> hit out‑of‑memory errors, lower `batch_size` in `config.json` or switch to the
> lighter `ViT-B-32` model.

---

## 5. ADB setup (phone connection)

The app talks to the phone through **ADB** (Android Debug Bridge).

1. **Install Platform Tools.** Download
   [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools),
   extract it (e.g. to `%LOCALAPPDATA%\Android\platform-tools`), and either:
   - add that folder to your **PATH**, **or**
   - set the full path to `adb.exe` in `config.json` → `"adb_path"`.

   Verify:

   ```powershell
   adb version
   ```

2. **Enable USB debugging on the phone:**
   - Settings → *About phone* → tap **Build number** 7 times to unlock
     *Developer options*.
   - Settings → *System* → *Developer options* → enable **USB debugging**.

3. **Connect the phone with a USB cable.** The first time, unlock the phone and
   tap **Allow** on the *"Allow USB debugging?"* prompt (tick *"Always allow from
   this computer"*).

4. Verify the phone is authorized:

   ```powershell
   adb devices
   # Should show:  <serial>    device
   # NOT:          <serial>    unauthorized
   ```

   If it says `unauthorized`, re‑check the on‑screen prompt. If it says nothing,
   re‑plug the cable and make sure the phone is set to *File transfer (MTP)* mode.

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for ADB problems.

---

## 6. Run

```powershell
python run.py
# or
python -m photo_ai_cleaner
```

On first launch the AI model weights are downloaded once and cached under
`%LOCALAPPDATA%\PhotoAICleaner\models`. This can take a minute depending on the
model and your connection.

Next: **[USAGE.md](USAGE.md)**.
