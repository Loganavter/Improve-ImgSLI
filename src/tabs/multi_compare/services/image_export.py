"""Saving helpers owned by the Multi Compare tab.

``save_composite`` is called off the GUI thread (see
:class:`tabs.multi_compare.services.save_flow.MultiCompareSaveFlowCoordinator`)
because PIL encoding of large composites (e.g. PNG with ``optimize=True``) can
take seconds and must not block the UI event loop.

The caller must convert the rendered ``QImage`` to a ``PIL.Image`` on the GUI
thread *before* handing it to the worker (mirrors
``plugins/export/services/gpu_export_proxy.py:_render_plan_frame``, which does
the ``QImage`` -> ``PIL.Image`` conversion inside the GUI-thread render call).
Touching a QRhi-backed ``QImage`` from a background thread is not safe — the
underlying GPU readback buffer/driver state is tied to the GUI thread, and
doing so was observed to deadlock the whole process.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

logger = logging.getLogger("ImproveImgSLI")


class _CancelableStream:
    """Wraps a file object so a long PIL encode can be aborted mid-write."""

    def __init__(self, base, cancel_event: Optional[threading.Event]):
        self._base = base
        self._cancel_event = cancel_event

    def write(self, b):
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise RuntimeError("Save canceled by user")
        return self._base.write(b)

    def flush(self):
        return self._base.flush()

    def close(self):
        return self._base.close()

    def seek(self, *args, **kwargs):
        return self._base.seek(*args, **kwargs)

    def tell(self):
        return self._base.tell()

    def writable(self):
        return True

    def readable(self):
        return False

    def seekable(self):
        return True

    def fileno(self):
        return self._base.fileno()


def save_composite(
    pil_image: Image.Image,
    options: dict,
    *,
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> str:
    def emit_progress(value: int) -> None:
        if progress_callback:
            progress_callback(value)

    t_total = time.perf_counter()
    output_dir = Path(options["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    image_format = str(options.get("format", "PNG")).upper()
    extension = ".jpg" if image_format == "JPEG" else f".{image_format.lower()}"
    output_path = _next_available_path(
        output_dir / f"{options['file_name']}{extension}"
    )
    emit_progress(30)

    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Save canceled by user")

    save_kwargs: dict = {}
    if image_format in {"JPEG", "BMP"}:
        t0 = time.perf_counter()
        background = tuple(options.get("background_color") or (255, 255, 255, 255))
        flattened = Image.new("RGBA", pil_image.size, background)
        flattened.alpha_composite(pil_image)
        pil_image = flattened.convert("RGB")
    if image_format in {"JPEG", "WEBP"}:
        save_kwargs["quality"] = int(options.get("quality", 95))
    if image_format == "PNG":
        save_kwargs["compress_level"] = int(options.get("png_compress_level", 9))
        save_kwargs["optimize"] = bool(options.get("png_optimize", True))
    emit_progress(50)

    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Save canceled by user")

    t0 = time.perf_counter()
    try:
        with open(output_path, "wb") as f:
            stream = _CancelableStream(f, cancel_event)
            pil_image.save(stream, format=image_format, **save_kwargs)
    except Exception:
        try:
            if output_path.exists():
                output_path.unlink()
        except Exception:
            pass
        raise
    emit_progress(100)
    return str(output_path)


def _next_available_path(path: Path) -> Path:
    """Return ``path`` or a suffixed variant that does not exist yet."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1
