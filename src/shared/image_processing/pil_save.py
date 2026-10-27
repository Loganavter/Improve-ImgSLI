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
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

SAVE_CANCELED_MESSAGE = "Save canceled by user"

_INVALID_FILENAME_CHARS = re.compile(r'[\\/*?:"<>|]')
_CONTROL_FILENAME_CHARS = re.compile(r"[\x00-\x1f\x7f]")

#: Windows device names: a file with one of these (case-insensitive) as the
#: stem before the first dot opens the device, not a file in the directory
#: (``CON.png``, ``NUL.txt``, ``COM1.jpg`` …). The write paths suffix ``_``.
RESERVED_DEVICE_STEMS: frozenset[str] = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
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


def is_reserved_device_stem(stem: str) -> bool:
    """True when ``stem`` names a Windows device rather than a file.

    Matching is case-insensitive and ignores trailing dots/spaces because
    Windows resolves ``CON``, ``con``, ``CON.`` and ``CON `` to the same
    device. Pass the stem up to the first dot (``CON.png`` → ``CON``).
    """
    if not stem:
        return False
    normalised = stem.strip().rstrip(".").strip().upper()
    return normalised in RESERVED_DEVICE_STEMS


def _suffix_reserved_stem(cleaned: str) -> str:
    """Append ``_`` when the pre-first-dot component is a device name."""
    head, separator, rest = cleaned.partition(".")
    if not is_reserved_device_stem(head):
        return cleaned
    return f"{head}_{separator}{rest}"


def _strip_trailing_dots_and_spaces(value: str) -> str:
    # Windows silently strips these, so ``report.`` and ``report `` create
    # ``report``; keeping them would desync the path we report from the file
    # that actually appears.
    return value.rstrip(" .")


def sanitize_export_basename(name: str, *, max_len: int = 120) -> str:
    """Strict boundary sanitiser for a user-supplied export file name.

    Unlike :func:`sanitize_filename_component` this *rejects* a name that
    cannot be a plain child of the chosen directory — a path separator, a
    drive prefix, a UNC prefix or a ``.``/``..`` traversal component — so a
    typed absolute path can never redirect the save. It raises ``ValueError``
    instead of rewriting, because silently turning ``/etc/passwd`` into
    ``_etc_passwd`` would hide a hostile/accidental input.

    Everything else is cleaned: control characters are removed, the Windows
    invalid set is replaced with ``_``, trailing dots/spaces are trimmed,
    reserved device stems get a ``_`` suffix, and the result is capped to
    ``max_len`` while staying non-empty.
    """
    if not isinstance(name, str):
        raise ValueError("Export name must be text")
    if not isinstance(max_len, int) or max_len < 1:
        raise ValueError("max_len must be a positive integer")

    raw = name.strip()
    if not raw:
        raise ValueError("Export name is empty")
    if "/" in raw or "\\" in raw:
        raise ValueError("Export name must not contain a path separator")
    # A bare drive spec ("C:") names a drive, not a file; "C:x" is a
    # drive-relative *path* only because of the colon, which the forgiving
    # rewrite below turns into an ordinary character ("C_x") — the separator
    # check above already covers every form that could still escape.
    if len(raw) == 2 and raw[1] == ":" and raw[0].isalpha():
        raise ValueError("Export name must not be a drive prefix")
    if raw in {".", ".."}:
        raise ValueError("Export name must not be a traversal component")

    cleaned = _CONTROL_FILENAME_CHARS.sub("", name)
    cleaned = _INVALID_FILENAME_CHARS.sub("_", cleaned)
    cleaned = _strip_trailing_dots_and_spaces(cleaned)
    if not cleaned:
        raise ValueError("Export name is empty after sanitizing")

    cleaned = _suffix_reserved_stem(cleaned)
    if len(cleaned) > max_len:
        cleaned = _strip_trailing_dots_and_spaces(cleaned[:max_len])
        if not cleaned:
            raise ValueError("Export name is empty after sanitizing")
        if is_reserved_device_stem(cleaned.partition(".")[0]):
            # Truncation produced a device name (``CONx`` → ``CON``); swap the
            # last character so the length cap still holds.
            cleaned = f"{cleaned[:-1]}_"
    return cleaned


def safe_child_path(directory: str, filename: str) -> Path:
    """Join ``filename`` under ``directory``, refusing anything that escapes.

    Write-boundary re-verification after :func:`sanitize_export_basename`:
    the joined path is accepted only when its resolved parent is the resolved
    ``directory``. A separator, an absolute path, a drive/UNC prefix or a
    traversal component therefore raises ``ValueError`` — the caller's save
    aborts through the normal error path and no file is written outside the
    directory the user picked.
    """
    if not isinstance(filename, str) or not filename:
        raise ValueError("Export name is empty")
    if "/" in filename or "\\" in filename:
        raise ValueError("Export name must not contain a path separator")

    directory_path = Path(directory)
    candidate = directory_path / filename
    try:
        resolved_directory = directory_path.resolve(strict=False)
        resolved_candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:  # symlink loop, unreadable parent
        raise ValueError(f"Cannot resolve export path: {exc}") from exc
    if resolved_candidate.parent != resolved_directory:
        raise ValueError("Export path escapes the chosen output directory")
    return candidate


def sanitize_filename_component(name: str, max_len: int = 80) -> str:
    """Forgiving filename component sanitiser — never raises.

    Used where a name is auto-derived (project auto-naming from a tab title)
    and failing is not an option. Applies the same rules as
    :func:`sanitize_export_basename` but rewrites instead of rejecting, and
    falls back to ``image`` when everything is stripped.
    """
    try:
        cleaned = str(name or "")
    except Exception:  # exotic __str__; a name we cannot read is not a name
        cleaned = ""
    cleaned = _CONTROL_FILENAME_CHARS.sub("", cleaned)
    cleaned = _INVALID_FILENAME_CHARS.sub("_", cleaned)
    cleaned = _strip_trailing_dots_and_spaces(cleaned)
    if not cleaned:
        return "image"
    cleaned = _suffix_reserved_stem(cleaned)

    try:
        limit = max(1, int(max_len))
    except (TypeError, ValueError):
        limit = 80
    if len(cleaned) > limit:
        cleaned = _strip_trailing_dots_and_spaces(cleaned[:limit])
        if not cleaned:
            return "image"
        if is_reserved_device_stem(cleaned.partition(".")[0]):
            cleaned = f"{cleaned[:-1]}_"
    return cleaned


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
            raise RuntimeError(SAVE_CANCELED_MESSAGE)
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


def write_pil_image_to_sink(
    pil_img: Image.Image,
    sink,
    pil_format: str,
    save_kwargs: dict,
    *,
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
    progress_start: int = 50,
    progress_end: int = 99,
) -> None:
    """Encode ``pil_img`` into an already-open binary *sink*.

    The stream-level half of :func:`write_pil_image_cancelable`, factored out
    for callers that own the target (e.g. the shared export writer writing to
    a caller-provided file object). No atomic publication happens here — the
    sink's owner decides what to do with a partially written stream on failure.
    """
    if progress_callback is not None:
        progress_callback(progress_start)

    expected_bytes = (
        estimate_encoded_size(pil_img, pil_format, save_kwargs)
        if progress_callback is not None
        else 0
    )
    stream = _CancelableStream(
        sink,
        cancel_event,
        progress_callback=progress_callback,
        progress_start=progress_start,
        progress_end=progress_end,
        expected_bytes=expected_bytes,
    )
    pil_img.save(stream, format=pil_format, **save_kwargs)


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

    Atomic via tmp+replace: the encoder writes to ``full_path.tmp`` in the
    same directory and the file is moved into place only on success, so a
    hard exit (os._exit in ``__main__.py:385``) mid-encode leaves the
    previous file intact (or no file) rather than a truncated image at the
    final path — same guarantee project packaging already has.

    Deletes a partial tmp file on failure. Caller owns ``os.makedirs`` for
    ``dirname(full_path)``. When ``progress_callback`` is set, encode progress
    is reported in ``[progress_start, progress_end]`` from bytes written;
    callers should emit 100 after a successful return.
    """
    if progress_callback is not None:
        progress_callback(progress_start)

    tmp_path = full_path + ".tmp"
    # If a stale tmp from a crashed previous run exists, remove it first so
    # open() below doesn't append to it.
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception:
        pass

    try:
        with open(tmp_path, "wb") as f:
            write_pil_image_to_sink(
                pil_img,
                f,
                pil_format,
                save_kwargs,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
                progress_start=progress_start,
                progress_end=progress_end,
            )
        os.replace(tmp_path, full_path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise