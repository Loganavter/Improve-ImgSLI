"""Clipboard paste for image_compare — direction dialog + shared coordinator.

Collect/split/download lives in ``shared.clipboard_paste``
(``ClipboardPasteCoordinator``); this service only wires collect →
direction dialog → coordinator → slot placement (keeps ``create_service``
contract and the ``PasteDirectionOverlay`` open site stable).
"""

import logging
from pathlib import Path

from sli_ui_toolkit.i18n import tr

from shared.clipboard_images import download_images_from_urls
from shared.clipboard_paste import (
    ClipboardPasteCoordinator,
    collect_clipboard_image_items,
)

logger = logging.getLogger("ImproveImgSLI")


class ClipboardService:
    def __init__(self, store, main_controller, widget):
        self.store = store
        self.main_controller = main_controller
        self.widget = widget
        self._paste_dialog = None

    def paste_image_from_clipboard(self):
        try:
            if self._paste_dialog is not None:
                try:
                    if self._paste_dialog.isVisible():
                        return False
                except Exception:
                    self._paste_dialog = None

            items_to_process = collect_clipboard_image_items()
            if not items_to_process:
                if self.main_controller:
                    self.main_controller.error_occurred.emit(
                        tr(
                            "msg.no_image_in_clipboard",
                            self.store.settings.current_language,
                        )
                    )
                return False

            self.show_paste_direction_dialog(items_to_process)
            return True

        except Exception as e:
            logger.error(f"Error in paste: {e}")
            return False

    def download_images_from_urls(self, urls: list[str], timeout: int = 10):
        return download_images_from_urls(urls, timeout)

    def show_paste_direction_dialog(self, items_to_process: list):
        try:
            main_window = None
            if self.main_controller and self.main_controller.window_shell:
                main_window = self.main_controller.window_shell.main_window_app
            if not main_window:
                return False

            def on_direction_selected(direction: str):
                slot_number = 1 if direction in ("up", "left") else 2

                def on_ready(paths: list[Path]) -> None:
                    if self.main_controller and self.main_controller.sessions:
                        self.main_controller.sessions.load_images_from_paths(
                            [str(p) for p in paths],
                            slot_number,
                        )

                def on_download_started(urls: list[str]) -> None:
                    if self.main_controller:
                        self.main_controller.error_occurred.emit(
                            tr(
                                "msg.loading_images_from_clipboard",
                                self.store.settings.current_language,
                            )
                        )

                thread_pool = None
                if self.main_controller:
                    thread_pool = self.main_controller.thread_pool
                coord = ClipboardPasteCoordinator(
                    thread_pool=thread_pool,
                    on_ready=on_ready,
                    on_download_started=on_download_started,
                )
                coord.run_with_items(list(items_to_process))

            from services.system.paste_direction_overlay import (
                show_paste_direction_overlay,
            )

            self._paste_dialog = show_paste_direction_overlay(
                parent=main_window,
                image_label=self.widget.image_label,
                is_horizontal=self.store.viewport.view_state.is_horizontal,
                language=self.store.settings.current_language,
                on_direction=on_direction_selected,
                on_cancelled=lambda: setattr(self, "_paste_dialog", None),
            )
            return True
        except Exception as e:
            logger.error(f"Overlay error: {e}")
