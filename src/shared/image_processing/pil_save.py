"""Shared helpers for saving PIL images to disk.

Common ground between each tab's still-image export service — filename
sanitization, collision-free path generation, background flattening for
non-alpha formats, comment metadata, and a cancelable write.
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger("ImproveImgSLI")

_INVALID_FILENAME_CHARS = re.compile(r'[\\/*?:"<>|]')
_FORMATS_WITH_ALPHA = frozenset({"PNG", "TIFF", "WEBP", "JXL"})
_MODE_BYTES_PER_PIXEL = {
    "1": 0.125,
    "L": 1,
    "P": 1,
    "RGB": 3,
    "RGBA": 4,
    "CMYK": 4,
    "LA": 2,
    "PA": 2,
}


def sanitize_filename_component(name: str, max_len: int = 80) -> str:
    """Strip filesystem-hostile characters and truncate."""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name)
    return cleaned[:max_len]


def next_available_path(path: Path, *, style: str = "paren") -> Path:
    """Return ``path`` or the first non-existing suffixed variant.

    ``style="paren"`` produces ``stem (1).ext`` (image-compare convention).
    ``style="underscore"`` produces ``stem_1.ext`` (multi-compare convention).
    """
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    template = " ({n})" if style == "paren" else "_{n}"
    index = 1
    while True:
        candidate = parent / f"{stem}{template.format(n=index)}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1





def estimate_encoded_size(
    pil_img: Image.Image,
    pil_format: str,
    save_kwargs: dict | None = None,
) -> int:
    """Heuristic expected on-disk size for progress mapping during encode.

    Prefer a mild overestimate so the bar keeps moving through the whole write
    instead of hitting the end early and stalling.
    """
    save_kwargs = save_kwargs or {}
    width, height = pil_img.size
    bpp = float(_MODE_BYTES_PER_PIXEL.get(pil_img.mode, 4))
    uncompressed = max(1, int(width * height * bpp))
    fmt = (pil_format or "PNG").upper()
    if fmt == "JPG":
        fmt = "JPEG"

    if fmt == "BMP":
        ratio = 1.05
    elif fmt == "TIFF":
        ratio = 0.85
    elif fmt == "JPEG":
        quality = int(save_kwargs.get("quality", 95))
        ratio = 0.12 + (max(1, min(100, quality)) / 100.0) * 0.28
    elif fmt == "WEBP":
        quality = int(save_kwargs.get("quality", 95))
        ratio = 0.08 + (max(1, min(100, quality)) / 100.0) * 0.22
    elif fmt == "PNG":
        compress = int(save_kwargs.get("compress_level", 6))
        compress = max(0, min(9, compress))
        # compress 9 → ~0.35, compress 0 → ~0.95 of uncompressed
        ratio = 0.35 + (9 - compress) * (0.60 / 9.0)
        if save_kwargs.get("optimize"):
            ratio *= 0.85
    else:
        ratio = 0.45

    return max(4096, int(uncompressed * ratio))


def progress_from_bytes_written(
    bytes_written: int,
    expected_bytes: int,
    *,
    progress_start: int,
    progress_end: int,
) -> int:
    """Map bytes written to ``[progress_start, progress_end]`` asymptotically.

    Never returns ``progress_end`` — callers should emit that (or 100) explicitly
    when the encode finishes. Extra bytes beyond the estimate keep crawling
    toward the end instead of freezing mid-bar.
    """
    start = max(0, min(100, int(progress_start)))
    end = max(start, min(100, int(progress_end)))
    if end <= start:
        return start
    expected = max(1, int(expected_bytes))
    written = max(0, int(bytes_written))
    # written == expected → ~63%; 3× expected → ~95%; always < 1.0
    fraction = min(0.99, 1.0 - math.exp(-written / float(expected)))
    return start + int((end - start) * fraction)


class _CancelableStream:
    """File-like wrapper that raises when ``cancel_event`` fires on write.

    Optionally reports encode progress from bytes flushed by the PIL encoder.
    """

    def __init__(
        self,
        base,
        cancel_event: Optional[threading.Event],
        *,
        progress_callback: Optional[Callable[[int], None]] = None,
        progress_start: int = 50,
        progress_end: int = 99,
        expected_bytes: int = 0,
    ) -> None:
        self._b = base
        self._e = cancel_event
        self._progress_callback = progress_callback
        self._progress_start = progress_start
        self._progress_end = progress_end
        self._expected_bytes = max(0, int(expected_bytes))
        self._bytes_written = 0
        self._last_emitted = progress_start - 1

    def write(self, b):
        if self._e is not None and self._e.is_set():
            raise RuntimeError("Save canceled by user")
        written = self._b.write(b)
        if self._progress_callback is not None and self._expected_bytes > 0:
            try:
                chunk_len = written if isinstance(written, int) and written >= 0 else len(b)
            except TypeError:
                chunk_len = 0
            self._bytes_written += max(0, int(chunk_len))
            value = progress_from_bytes_written(
                self._bytes_written,
                self._expected_bytes,
                progress_start=self._progress_start,
                progress_end=self._progress_end,
            )
            if value > self._last_emitted:
                self._last_emitted = value
                self._progress_callback(value)
        return written

    def flush(self):
        return self._b.flush()

    def close(self):
        return self._b.close()

    def seek(self, *args, **kwargs):
        return self._b.seek(*args, **kwargs)

    def tell(self):
        return self._b.tell()

    def writable(self):
        return True

    def readable(self):
        return False

    def seekable(self):
        return True

    def fileno(self):
        return self._b.fileno()


def write_pil_image_cancelable(
    pil_img: Image.Image,
    full_path: str,
    pil_format: str,
    save_kwargs: dict,
    *,
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
    progress_start: int = 50,
    progress_end: int = 99,
) -> None:
    """Write ``pil_img`` to ``full_path`` via a cancelable stream.

    Deletes a partial file on failure. Caller owns ``os.makedirs`` for
    ``dirname(full_path)``. When ``progress_callback`` is set, encode progress
    is reported in ``[progress_start, progress_end]`` from bytes written;
    callers should emit 100 after a successful return.
    """
    if progress_callback is not None:
        progress_callback(progress_start)

    expected_bytes = (
        estimate_encoded_size(pil_img, pil_format, save_kwargs)
        if progress_callback is not None
        else 0
    )

    try:
        with open(full_path, "wb") as f:
            stream = _CancelableStream(
                f,
                cancel_event,
                progress_callback=progress_callback,
                progress_start=progress_start,
                progress_end=progress_end,
                expected_bytes=expected_bytes,
            )
            pil_img.save(stream, format=pil_format, **save_kwargs)
    except Exception:
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception:
            pass
        raise