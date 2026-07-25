"""Small human-readable formatting helpers for the GUI."""

from __future__ import annotations


def human_size(num_bytes: int) -> str:
    """Format a byte count as a human readable string (e.g. ``12.3 MB``)."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def format_eta(seconds: float) -> str:
    """Format an ETA in seconds as ``mm:ss`` or ``hh:mm:ss``."""
    seconds = int(max(0, seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes:02d}m {secs:02d}s"
