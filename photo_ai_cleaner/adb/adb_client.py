"""A thin, well-typed wrapper around the ADB command line tool.

This is the *only* module that shells out to ``adb``. It handles:

* detecting whether ADB is installed and on PATH,
* reporting device connection / authorization state clearly,
* listing image files inside the configured folders,
* streaming a single image's bytes to RAM (never to disk),
* pulling thumbnails on demand,
* deleting files with ``adb shell rm``.

The client copies images "one file at a time" via ``adb exec-out cat`` so
that the whole photo library is never copied to the PC.
"""

from __future__ import annotations

import subprocess
from typing import Iterable, List, Optional

from ..models.data_models import DeviceInfo, DeviceState, RemoteFile
from ..utils.logging_config import get_logger

_logger = get_logger(__name__)

# Recognised image extensions (lower-case, no dot).
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic", "heif", "bmp", "gif"}

# Prevent GUI flashing of console windows on Windows.
_CREATE_NO_WINDOW = 0x08000000


class AdbError(RuntimeError):
    """Raised when an ADB command fails unexpectedly."""


class AdbClient:
    """High level interface to a single USB-connected Android device."""

    def __init__(self, adb_path: str = "adb", serial: Optional[str] = None) -> None:
        """Create a client.

        Args:
            adb_path: Path to the ``adb`` executable (``adb`` if on PATH).
            serial: Optional device serial to target a specific device.
        """
        self._adb_path = adb_path
        self._serial = serial

    # ------------------------------------------------------------------ #
    # Low level command execution
    # ------------------------------------------------------------------ #
    def _base_cmd(self) -> List[str]:
        cmd = [self._adb_path]
        if self._serial:
            cmd += ["-s", self._serial]
        return cmd

    def _run(
        self, args: List[str], timeout: float = 30.0, binary: bool = False
    ) -> subprocess.CompletedProcess:
        """Run an adb command and return the completed process."""
        cmd = self._base_cmd() + args
        _logger.debug("Running adb: %s", " ".join(cmd))
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=not binary,
                timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AdbError("adb executable not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"adb command timed out: {' '.join(args)}") from exc

    # ------------------------------------------------------------------ #
    # Device detection
    # ------------------------------------------------------------------ #
    def is_available(self) -> bool:
        """Return True when the adb executable can be launched."""
        try:
            result = self._run(["version"], timeout=10)
            return result.returncode == 0
        except AdbError:
            return False

    def device_info(self) -> DeviceInfo:
        """Detect the device state and return a descriptive :class:`DeviceInfo`."""
        if not self.is_available():
            return DeviceInfo(
                state=DeviceState.NO_ADB,
                message=(
                    "ADB non trovato. Installa Android Platform Tools e "
                    "assicurati che 'adb' sia nel PATH."
                ),
            )

        try:
            result = self._run(["devices", "-l"], timeout=15)
        except AdbError as exc:
            return DeviceInfo(state=DeviceState.NO_ADB, message=str(exc))

        lines = [ln.strip() for ln in result.stdout.splitlines()[1:] if ln.strip()]
        if not lines:
            return DeviceInfo(
                state=DeviceState.NO_DEVICE,
                message="Nessun dispositivo rilevato. Collega il telefono via USB.",
            )

        for line in lines:
            parts = line.split()
            serial, status = parts[0], parts[1]
            model = self._extract_model(parts)
            if status == "unauthorized":
                return DeviceInfo(
                    state=DeviceState.UNAUTHORIZED,
                    serial=serial,
                    message=(
                        "Dispositivo non autorizzato. Sblocca il telefono e "
                        "conferma 'Consenti debug USB' sullo schermo."
                    ),
                )
            if status == "offline":
                return DeviceInfo(
                    state=DeviceState.OFFLINE,
                    serial=serial,
                    message="Dispositivo offline. Riconnetti il cavo USB.",
                )
            if status == "device":
                self._serial = self._serial or serial
                return DeviceInfo(
                    state=DeviceState.CONNECTED,
                    serial=serial,
                    model=model,
                    message=f"Connesso: {model or serial}",
                )

        return DeviceInfo(
            state=DeviceState.NO_DEVICE,
            message="Stato dispositivo sconosciuto.",
        )

    @staticmethod
    def _extract_model(parts: List[str]) -> Optional[str]:
        for token in parts:
            if token.startswith("model:"):
                return token.split(":", 1)[1]
        return None

    # ------------------------------------------------------------------ #
    # File discovery
    # ------------------------------------------------------------------ #
    def list_images(self, folders: Iterable[str]) -> List[RemoteFile]:
        """List all image files inside ``folders`` on the phone.

        Uses a single ``find`` invocation per folder. Files are returned with
        their size and modification time so the pipeline can skip unchanged
        entries and compute total sizes without extra round-trips.
        """
        files: List[RemoteFile] = []
        for folder in folders:
            files.extend(self._list_folder(folder))
        _logger.info("Discovered %d image files across %d folders", len(files), len(list(folders)))
        return files

    def _list_folder(self, folder: str) -> List[RemoteFile]:
        # find ... -printf is not available on Android's toolbox, so we use
        # `-exec stat` via a portable shell one-liner returning: path|size|mtime
        name_filters = " -o ".join(f'-iname "*.{ext}"' for ext in sorted(IMAGE_EXTENSIONS))
        # ``-not -path "*/.*"`` prunes hidden directories/files (e.g. Android's
        # own ``.thumbnails`` cache), which are not real user photos.
        script = (
            f'find "{folder}" -type f \\( {name_filters} \\) '
            r'-not -path "*/.*" '
            r'-exec stat -c "%n|%s|%Y" {} \; 2>/dev/null'
        )
        result = self._run(["shell", script], timeout=180)
        files: List[RemoteFile] = []
        for line in result.stdout.splitlines():
            parsed = self._parse_stat_line(line)
            if parsed is not None:
                files.append(parsed)
        _logger.debug("Folder %s -> %d images", folder, len(files))
        return files

    @staticmethod
    def _parse_stat_line(line: str) -> Optional[RemoteFile]:
        line = line.strip()
        if not line or "|" not in line:
            return None
        try:
            path, size, mtime = line.rsplit("|", 2)
            return RemoteFile(path=path, size=int(size), mtime=int(mtime))
        except (ValueError, IndexError):
            return None

    # ------------------------------------------------------------------ #
    # Streaming file access
    # ------------------------------------------------------------------ #
    def read_file(self, phone_path: str, timeout: float = 60.0) -> Optional[bytes]:
        """Stream a single file's bytes into memory (never touches disk).

        Returns ``None`` if the file could not be read.
        """
        # The command must be a SINGLE argument so the device shell parses the
        # quotes. Passing "cat" and the quoted path as separate argv makes the
        # quotes reach `cat` literally on Windows -> "No such file" errors.
        cmd = self._base_cmd() + ["exec-out", f"cat {self._quote(phone_path)}"]
        _logger.debug("Streaming file: %s", phone_path)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            _logger.warning("Failed to stream %s: %s", phone_path, exc)
            return None
        if result.returncode != 0 or not result.stdout:
            _logger.warning("Empty/failed read for %s (rc=%s)", phone_path, result.returncode)
            return None
        return result.stdout

    # ------------------------------------------------------------------ #
    # Deletion
    # ------------------------------------------------------------------ #
    def delete_files(self, phone_paths: Iterable[str]) -> List[str]:
        """Delete files on the phone via ``adb shell rm``.

        Returns the list of paths that were successfully removed.
        """
        removed: List[str] = []
        for path in phone_paths:
            # Single-argument command so the device shell handles the quoting
            # (same reason as in read_file).
            result = self._run(["shell", f"rm -f {self._quote(path)}"], timeout=30)
            if result.returncode == 0:
                removed.append(path)
                _logger.info("Deleted on device: %s", path)
            else:
                _logger.error("Failed to delete %s: %s", path, result.stderr)
        return removed

    @staticmethod
    def _quote(path: str) -> str:
        """Quote a remote path for the Android shell."""
        escaped = path.replace("'", "'\\''")
        return f"'{escaped}'"
