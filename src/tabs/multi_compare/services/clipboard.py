"""Clipboard paste for multi_compare — cursor DnD placement like file drop.

Collect/split/download lives in ``shared.clipboard_paste``
(``ClipboardPasteCoordinator``); this service only wires the coordinator
→ ``controller.begin_paste_placement``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sli_ui_toolkit.i18n import tr

from shared.clipboard_paste import ClipboardPasteCoordinator
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


class ClipboardService:
    """Paste clipboard images via direct async load (P3A, IC parity).

    Previously started ``begin_pending_paste`` so the drop highlight
    followed the cursor until a click; now ``begin_paste_placement``
    auto-places through the P2 worker path (imageless slot + loading toast
    immediately, no click-to-place, no armed highlight).
    """

    def __init__(self, store, main_controller, controller):
        self.store = store
        self.main_controller = main_controller
        self.controller = controller

    def paste_image_from_clipboard(self) -> bool:
        try:
            thread_pool = getattr(self.main_controller, "thread_pool", None)

            def on_ready(paths: list[Path]) -> None:
                self.controller.begin_paste_placement(paths)

            def on_empty() -> None:
                if self.main_controller:
                    self.main_controller.error_occurred.emit(
                        tr(
                            "msg.no_image_in_clipboard",
                            self.store.settings.current_language,
                        )
                    )

            def on_download_started(urls: list[str]) -> None:
                if self.main_controller:
                    self.main_controller.error_occurred.emit(
                        tr(
                            "msg.loading_images_from_clipboard",
                            self.store.settings.current_language,
                        )
                    )

            coord = ClipboardPasteCoordinator(
                thread_pool=thread_pool,
                on_ready=on_ready,
                on_empty=on_empty,
                on_download_started=on_download_started,
            )
            return coord.run()
        except Exception as e:
            logger.error("Error in multi_compare paste: %s", e)
            return False
