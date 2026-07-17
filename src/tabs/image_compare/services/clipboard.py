import logging
import os

from sli_ui_toolkit.i18n import tr
from sli_ui_toolkit.workers import GenericWorker

from shared.clipboard_images import (
    collect_clipboard_image_items,
    download_images_from_urls,
)

logger = logging.getLogger("ImproveImgSLI")


class ClipboardService:
    def __init__(self, store, main_controller, widget):
        self.store = store
        self.main_controller = main_controller
        self.widget = widget
        self._paste_dialog = None
        self._paste_overlay_canvas = None

    def paste_image_from_clipboard(self):
        try:
            if self._paste_dialog is not None:
                try:
                    if self._paste_dialog.isVisible():
                        return False
                except Exception:
                    self._paste_dialog = None
            if (
                self._paste_overlay_canvas is not None
                and self._paste_overlay_canvas.is_paste_overlay_visible()
            ):
                return False

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
                self._clear_canvas_paste_overlay()
                slot_number = 1 if direction in ("up", "left") else 2

                local_files = [i for i in items_to_process if os.path.exists(i)]
                urls = [i for i in items_to_process if i.startswith("http")]

                if local_files and self.main_controller and self.main_controller.sessions:
                    self.main_controller.sessions.load_images_from_paths(
                        local_files,
                        slot_number,
                    )

                if urls:
                    if self.main_controller:
                        self.main_controller.error_occurred.emit(
                            tr(
                                "msg.loading_images_from_clipboard",
                                self.store.settings.current_language,
                            )
                        )
                    worker = GenericWorker(self.download_images_from_urls, urls, 15)

                    if self.main_controller and self.main_controller.sessions:
                        worker.signals.result.connect(
                            lambda paths: (
                                self.main_controller.sessions.load_images_from_paths(
                                    paths,
                                    slot_number,
                                )
                                if self.main_controller
                                and self.main_controller.sessions
                                else None
                            )
                        )
                        self.main_controller.thread_pool.start(worker)

            from services.system.paste_direction_overlay import (
                PasteDirectionOverlay,
            )

            self._clear_canvas_paste_overlay()
            overlay = PasteDirectionOverlay(
                main_window,
                self.widget.image_label,
                is_horizontal=self.store.viewport.view_state.is_horizontal,
            )
            overlay.set_language(self.store.settings.current_language)
            self._paste_dialog = overlay
            overlay.direction_selected.connect(on_direction_selected)
            overlay.cancelled.connect(lambda: setattr(self, "_paste_dialog", None))
            overlay.show_overlay()
            return True
        except Exception as e:
            logger.error(f"Overlay error: {e}")

    def _clear_canvas_paste_overlay(self):
        canvas = self._paste_overlay_canvas
        self._paste_overlay_canvas = None
        if canvas is None:
            return
        try:
            canvas.pasteOverlayDirectionSelected.disconnect()
        except Exception:
            pass
        try:
            canvas.pasteOverlayCancelled.disconnect()
        except Exception:
            pass
        try:
            canvas.set_paste_overlay_state(False)
        except Exception:
            pass
