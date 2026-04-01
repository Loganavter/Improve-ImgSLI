import logging
import os
import tempfile
import time
import urllib.request

from PyQt6.QtWidgets import QApplication

from resources.translations import tr
from shared_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

class ClipboardService:

    def __init__(self, store, main_controller, image_loader_service=None):
        self.store = store
        self.main_controller = main_controller
        self.image_loader = image_loader_service
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

            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()

            items_to_process = []

            text_content = mime_data.text()
            if text_content:
                for line in text_content.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue

                    if os.path.exists(line) or line.startswith("file://"):
                        path = line[7:] if line.startswith("file://") else line
                        if os.path.exists(path):
                            items_to_process.append(path)

                    elif line.startswith(("http://", "https://")):
                        items_to_process.append(line)

            if mime_data.hasUrls():
                for url in mime_data.urls():
                    url_str = url.toString()
                    if url.isLocalFile():
                        items_to_process.append(url.toLocalFile())
                    elif url_str.startswith(("http://", "https://")):
                        items_to_process.append(url_str)

            if not items_to_process and mime_data.hasImage():
                qimage = clipboard.image()
                if not qimage.isNull():
                    temp_path = os.path.join(
                        tempfile.gettempdir(), f"clip_{int(time.time()*1000)}.png"
                    )
                    qimage.save(temp_path, "PNG")
                    items_to_process.append(temp_path)

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
        downloaded_paths = []
        try:
            for url_str in urls:
                try:
                    with urllib.request.urlopen(url_str, timeout=timeout) as response:
                        content_type = response.headers.get_content_type()
                        if content_type and content_type.startswith("image/"):
                            temp_dir = tempfile.gettempdir()
                            timestamp = int(time.time() * 1000)
                            ext = (content_type.split("/")[-1] or "png").lower()
                            if ext == "jpeg":
                                ext = "jpg"
                            temp_filename = f"url_image_{os.getpid()}_{timestamp}.{ext}"
                            image_path = os.path.join(temp_dir, temp_filename)
                            with open(image_path, "wb") as f:
                                f.write(response.read())
                            downloaded_paths.append(image_path)
                except Exception as e:
                    logger.warning(f"Failed to download image from URL {url_str}: {e}")
            return downloaded_paths
        except Exception as e:
            logger.error(f"Unexpected error during URL downloads: {e}")
            return downloaded_paths

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
                        local_files, slot_number
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
                                    paths, slot_number
                                )
                                if self.main_controller
                                and self.main_controller.sessions
                                else None
                            )
                        )
                        self.main_controller.thread_pool.start(worker)

            image_label = getattr(main_window.ui, "image_label", None)
            if image_label and hasattr(image_label, "set_paste_overlay_state"):
                self._clear_canvas_paste_overlay()
                self._paste_overlay_canvas = image_label
                image_label.pasteOverlayDirectionSelected.connect(
                    on_direction_selected
                )
                image_label.pasteOverlayCancelled.connect(
                    self._clear_canvas_paste_overlay
                )
                image_label.set_paste_overlay_state(
                    True,
                    is_horizontal=self.store.viewport.view_state.is_horizontal,
                    texts={
                        "up": tr("common.position.up", self.store.settings.current_language),
                        "down": tr("common.position.down", self.store.settings.current_language),
                        "left": tr("common.position.left", self.store.settings.current_language),
                        "right": tr("common.position.right", self.store.settings.current_language),
                    },
                )
                image_label.setFocus()
                return True

            from shared_toolkit.ui.widgets.paste_direction_overlay import (
                PasteDirectionOverlay,
            )

            overlay = PasteDirectionOverlay(
                main_window,
                main_window.ui.image_label,
                is_horizontal=self.store.viewport.view_state.is_horizontal,
            )
            overlay.set_language(self.store.settings.current_language)
            self._paste_dialog = overlay
            overlay.direction_selected.connect(on_direction_selected)
            overlay.cancelled.connect(lambda: setattr(self, "_paste_dialog", None))
            overlay.show()
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
