"""Paste-direction insert for images delivered via Move (image carry).

Same UX as Duplicate / Ctrl+V: pick left/right (or up/down), then load.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tabs.image_compare.tab import ImageCompareTab

logger = logging.getLogger("ImproveImgSLI")

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".jxl"}


def begin_pending_image_insert(tab: "ImageCompareTab", paths) -> bool:
    widget = tab._widget
    if widget is None:
        return False
    canvas = getattr(widget, "image_label", None)
    if canvas is None:
        return False
    parent = canvas.window()
    if parent is None:
        return False

    image_paths = [
        str(p)
        for p in (Path(x) for x in paths)
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
    ]
    if not image_paths:
        return False

    main_window = (
        getattr(widget._context, "main_window", None) if widget._context else None
    )
    if main_window is None:
        main_window = parent
    controller = getattr(main_window, "main_controller", None)
    if controller is None:
        presenter = getattr(main_window, "presenter", None)
        controller = getattr(presenter, "main_controller", None)
    sessions = getattr(controller, "sessions", None) if controller else None
    if sessions is None or not hasattr(sessions, "load_images_from_paths"):
        logger.warning("begin_pending_image_insert: sessions controller unavailable")
        return False

    store = getattr(main_window, "store", None)
    if store is None:
        presenter = getattr(main_window, "presenter", None)
        store = getattr(presenter, "store", None) if presenter is not None else None
    is_horizontal = False
    language = "en"
    if store is not None:
        try:
            is_horizontal = bool(store.viewport.view_state.is_horizontal)
            language = store.settings.current_language or "en"
        except Exception:
            pass

    def on_dir(direction: str) -> None:
        target = 1 if direction in ("up", "left") else 2
        sessions.load_images_from_paths(image_paths, target)

    from services.system.paste_direction_overlay import show_paste_direction_overlay

    show_paste_direction_overlay(
        parent=parent,
        image_label=canvas,
        is_horizontal=is_horizontal,
        language=language,
        on_direction=on_dir,
    )
    return True
