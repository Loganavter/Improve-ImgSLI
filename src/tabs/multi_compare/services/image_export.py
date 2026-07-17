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
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from shared.image_processing.pil_save import (
    next_available_path,
    write_pil_image_cancelable,
)

logger = logging.getLogger("ImproveImgSLI")


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

    output_dir = Path(options["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    image_format = str(options.get("format", "PNG")).upper()
    extension = ".jpg" if image_format == "JPEG" else f".{image_format.lower()}"
    output_path = next_available_path(
        output_dir / f"{options['file_name']}{extension}",
        style="underscore",
    )
    emit_progress(5)

    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Save canceled by user")

    save_kwargs: dict = {}
    if image_format in {"JPEG", "BMP"}:
        background = tuple(options.get("background_color") or (255, 255, 255, 255))
        flattened = Image.new("RGBA", pil_image.size, background)
        flattened.alpha_composite(pil_image)
        pil_image = flattened.convert("RGB")
    if image_format in {"JPEG", "WEBP"}:
        save_kwargs["quality"] = int(options.get("quality", 95))
    if image_format == "PNG":
        save_kwargs["compress_level"] = int(options.get("png_compress_level", 9))
        save_kwargs["optimize"] = bool(options.get("png_optimize", True))
    emit_progress(10)

    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Save canceled by user")

    write_pil_image_cancelable(
        pil_image,
        str(output_path),
        image_format,
        save_kwargs,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
        progress_start=10,
        progress_end=99,
    )
    emit_progress(100)
    return str(output_path)
