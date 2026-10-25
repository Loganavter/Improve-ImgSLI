"""Clipboard paste for image_gallery — reuses shared paste coordinator.

Paste is routed via ``TabRegistry.create_service("clipboard_paste_service")``
like IC/MC (``plugins/export/controller.py:69``). Gallery placement is
``controller.open_paths`` (file-drop style) — single source for local vs
downloaded http URLs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from shared.clipboard_paste import ClipboardPasteCoordinator
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


class ClipboardService:
    """Gallery paste: clipboard → ``GalleryController.open_paths``."""

    def __init__(self, store, main_controller, controller):
        # ``store``/``main_controller`` kept for TabRegistry signature parity
        # (IC/MC take them); gallery only needs controller + thread_pool.
        self.store = store
        self.main_controller = main_controller
        self.controller = controller

    def paste_image_from_clipboard(self) -> bool:
        try:
            # Shared coordinator handles collect/split/download; tab handles placement.
            # Uses ``main_controller.thread_pool`` when available (async download).
            thread_pool = getattr(self.main_controller, "thread_pool", None)

            def on_ready(paths: list[Path]) -> None:
                # Gallery path: open_paths handles dedup + folder vs files
                try:
                    self.controller.open_paths(paths)
                except Exception as e:
                    logger.error("gallery paste open_paths failed: %s", e)

            coord = ClipboardPasteCoordinator(
                thread_pool=thread_pool,
                on_ready=on_ready,
                on_empty=lambda: logger.debug("gallery paste: no image in clipboard"),
            )
            return coord.run()
        except Exception as e:
            logger.error("Error in gallery paste: %s", e)
            return False
