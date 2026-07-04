"""Shared helpers for saving PIL images to disk.

Common ground between ``tabs/image_compare/services/image_export.py`` and
``tabs/multi_compare/services/image_export.py`` — filename sanitization,
collision-free path generation, background flattening for non-alpha formats,
comment metadata, and a cancelable write.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger("ImproveImgSLI")

_INVALID_FILENAME_CHARS = re.compile(r'[\\/*?:"<>|]')
_FORMATS_WITH_ALPHA = frozenset({"PNG", "TIFF", "WEBP", "JXL"})


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


def flatten_rgba_over_background(
    pil_img: Image.Image,
    background_color,
    *,
    convert_to: str = "RGB",
) -> Image.Image:
    """Composite ``pil_img`` over ``background_color`` and return ``convert_to`` mode."""
    background_color = tuple(background_color) if background_color else (255, 255, 255, 255)
    if len(background_color) == 3:
        background_color = (*background_color, 255)
    flat = Image.new("RGBA", pil_img.size, background_color)
    if pil_img.mode == "RGBA":
        flat.alpha_composite(pil_img)
    else:
        flat.paste(pil_img)
    return flat.convert(convert_to) if convert_to != "RGBA" else flat


def format_needs_alpha_flatten(pil_format: str, pil_mode: str) -> bool:
    """True if ``pil_format`` can't carry alpha and ``pil_img`` has RGBA."""
    return pil_format.upper() not in _FORMATS_WITH_ALPHA and pil_mode == "RGBA"


def attach_comment_metadata(
    pil_img: Image.Image,
    save_kwargs: dict,
    pil_format: str,
    comment_text: str,
) -> None:
    """Attach ``comment_text`` to ``save_kwargs`` for supported PIL formats.

    Mutates ``save_kwargs`` in place. Silently ignores unsupported formats and
    errors — export shouldn't fail because a metadata attach failed.
    """
    try:
        if pil_format == "PNG":
            import PIL.PngImagePlugin as PngImagePlugin

            meta = PngImagePlugin.PngInfo()
            meta.add_text("Comment", comment_text)
            save_kwargs["pnginfo"] = meta
            return

        exif = pil_img.getexif()
        exif[0x9286] = comment_text
        save_kwargs["exif"] = exif.tobytes()
    except Exception:
        logger.debug(
            "Failed to attach export comment metadata for format=%s",
            pil_format,
            exc_info=True,
        )


class _CancelableStream:
    """File-like wrapper that raises when ``cancel_event`` fires on write."""

    def __init__(self, base, cancel_event: Optional[threading.Event]) -> None:
        self._b = base
        self._e = cancel_event

    def write(self, b):
        if self._e is not None and self._e.is_set():
            raise RuntimeError("Save canceled by user")
        return self._b.write(b)

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
) -> None:
    """Write ``pil_img`` to ``full_path`` via a cancelable stream.

    Deletes a partial file on failure. Caller owns ``os.makedirs`` for
    ``dirname(full_path)``.
    """
    try:
        with open(full_path, "wb") as f:
            stream = _CancelableStream(f, cancel_event)
            pil_img.save(stream, format=pil_format, **save_kwargs)
    except Exception:
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception:
            pass
        raise
