"""Clipboard paste for multi_compare — cursor DnD placement like file drop."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sli_ui_toolkit.i18n import tr
from sli_ui_toolkit.workers import GenericWorker

from shared.clipboard_images import (
    collect_clipboard_image_items,
    download_images_from_urls,
)

logger = logging.getLogger("ImproveImgSLI")


class ClipboardService:
    """Paste clipboard images via the same external DnD placement cycle.

    Starts ``begin_pending_paste`` so the drop highlight follows the cursor;
    a click drops through ``images_dropped`` → ``_on_images_dropped``.
    """

    def __init__(self, store, main_controller, controller):
        self.store = store
        self.main_controller = main_controller
        self.controller = controller

    def paste_image_from_clipboard(self) -> bool:
        try:
            items = collect_clipboard_image_items()
            if not items:
                if self.main_controller:
                    self.main_controller.error_occurred.emit(
                        tr(
                            "msg.no_image_in_clipboard",
                            self.store.settings.current_language,
                        )
                    )
                return False

            local_files = [i for i in items if os.path.exists(i)]
            urls = [i for i in items if i.startswith("http")]

            if not local_files and not urls:
                return False

            if urls:
                self._pending_local = [Path(p) for p in local_files]
                if self.main_controller:
                    self.main_controller.error_occurred.emit(
                        tr(
                            "msg.loading_images_from_clipboard",
                            self.store.settings.current_language,
                        )
                    )
                worker = GenericWorker(download_images_from_urls, urls, 15)
                worker.signals.result.connect(self._on_urls_downloaded)
                if self.main_controller and self.main_controller.thread_pool:
                    self.main_controller.thread_pool.start(worker)
                else:
                    paths = download_images_from_urls(urls, 15)
                    self._on_urls_downloaded(paths)
                return True

            self.controller.begin_paste_placement([Path(p) for p in local_files])
            return True
        except Exception as e:
            logger.error("Error in multi_compare paste: %s", e)
            return False

    def _on_urls_downloaded(self, paths: list[str] | None) -> None:
        pending = getattr(self, "_pending_local", []) or []
        self._pending_local = []
        downloaded = [Path(p) for p in (paths or []) if os.path.exists(p)]
        combined = list(pending) + downloaded
        if combined:
            self.controller.begin_paste_placement(combined)
