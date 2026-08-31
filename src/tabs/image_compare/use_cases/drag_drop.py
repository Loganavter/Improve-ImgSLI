"""External file-drop handling for ``ImageCompareTab`` -- split out to keep
that class down to the ``TabContract`` surface itself. ``accepts_drop``/
``handle_drop`` are required ``TabContract`` method names, so ``tab.py``
keeps thin delegators of those exact names.
"""

from __future__ import annotations

import logging
from pathlib import Path

from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _IMAGE_EXTENSIONS
from tabs.image_compare.debug import ic_dnd_debug as _dnd_log

logger = logging.getLogger("ImproveImgSLI")


def accepts_drop(paths: list[Path]) -> bool:
    _dnd_log("accepts_drop: %d paths %r", len(paths), paths[:3])
    for p in paths:
        ok = p.suffix.lower() in _IMAGE_EXTENSIONS
        if ok:
            _dnd_log("  accepts_drop: %s suffix=%s -> True", p, p.suffix.lower())
            return True
        _dnd_log("  accepts_drop: %s suffix=%s -> False", p, p.suffix.lower())
    return False


def handle_drop(tab, paths: list[Path], hint: dict | None = None) -> bool:
    from PySide6.QtCore import QTimer

    _dnd_log("handle_drop: ENTER %d paths %r hint=%r", len(paths), paths[:5], hint)
    widget = tab._widget
    if widget is None:
        _dnd_log("handle_drop: widget is None -> False")
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
    _dnd_log("handle_drop: filtered %d/%d image_paths %r", len(image_paths), len(paths), image_paths[:3])
    if not image_paths:
        _dnd_log("handle_drop: no supported image paths -> False")
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
    _dnd_log("handle_drop: scheduling load slot=%s paths=%r", slot, image_paths[:3])
    def _do_load():
        _dnd_log("handle_drop: _do_load executing load_images_from_paths slot=%s paths=%r", slot, image_paths[:3])
        try:
            sessions.load_images_from_paths(image_paths, slot)
            _dnd_log("handle_drop: _do_load done")
        except Exception as e:
            _dnd_log("handle_drop: _do_load failed %r", e)
    QTimer.singleShot(
        0, _do_load
    )
    _dnd_log("handle_drop: scheduled, returning True (overlay should already be hidden by WindowEventHandler)")
    return True
