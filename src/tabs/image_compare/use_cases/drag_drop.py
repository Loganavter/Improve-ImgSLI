"""External file-drop handling for ``ImageCompareTab`` -- split out to keep
that class down to the ``TabContract`` surface itself. ``accepts_drop``/
``handle_drop`` are required ``TabContract`` method names, so ``tab.py``
keeps thin delegators of those exact names.
"""

from __future__ import annotations

import logging
from pathlib import Path

from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _IMAGE_EXTENSIONS

logger = logging.getLogger("ImproveImgSLI")


def accepts_drop(paths: list[Path]) -> bool:
    return any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in paths)


def handle_drop(tab, paths: list[Path], hint: dict | None = None) -> bool:
    from PySide6.QtCore import QTimer

    widget = tab._widget
    if widget is None:
        logger.warning("ImageCompareTab.handle_drop: widget is not initialized")
        return False
    main_window = getattr(widget._context, "main_window", None) if widget._context else None
    if main_window is None:
        logger.warning("ImageCompareTab.handle_drop: main_window is unavailable")
        return False
    controller = getattr(main_window, "main_controller", None)
    if controller is None:
        presenter = getattr(main_window, "presenter", None)
        controller = getattr(presenter, "main_controller", None)
    sessions = getattr(controller, "sessions", None) if controller else None
    if sessions is None:
        logger.warning(
            "ImageCompareTab.handle_drop: sessions controller unavailable "
            "(main_controller=%r presenter=%r)",
            getattr(main_window, "main_controller", None),
            getattr(main_window, "presenter", None),
        )
        return False
    image_paths = [str(p) for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
    if not image_paths:
        logger.warning(
            "ImageCompareTab.handle_drop: no supported image paths in %s",
            paths,
        )
        return False
    slot = 1
    if hint is not None:
        if "slot" in hint:
            slot = 1 if int(hint.get("slot") or 1) == 1 else 2
        elif "is_left_area" in hint:
            slot = 1 if bool(hint.get("is_left_area")) else 2
    QTimer.singleShot(
        0, lambda: sessions.load_images_from_paths(image_paths, slot)
    )
    return True
