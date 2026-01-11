

import logging
import os
import tempfile
import time
import urllib.request

from PIL import Image
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from shared_toolkit.workers import GenericWorker
from resources.translations import tr

logger = logging.getLogger("ImproveImgSLI")

class ClipboardService:

    def __init__(self, store, main_controller, image_loader_service=None):
        self.store = store
        self.main_controller = main_controller
        self.image_loader = image_loader_service
        self._paste_dialog = None

    def paste_image_from_clipboard(self):
        try:

            if self._paste_dialog is not None:
                try:
                    if self._paste_dialog.isVisible(): return False
                except: self._paste_dialog = None

            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()

            items_to_process = []

            text_content = mime_data.text()
            if text_content:
                for line in text_content.strip().split('\n'):
                    line = line.strip()
                    if not line: continue

                    if os.path.exists(line) or line.startswith('file://'):
                        path = line[7:] if line.startswith('file://') else line
                        if os.path.exists(path): items_to_process.append(path)

                    elif line.startswith(('http://', 'https://')):
                        items_to_process.append(line)

            if mime_data.hasUrls():
                for url in mime_data.urls():
                    url_str = url.toString()
                    if url.isLocalFile():
                        items_to_process.append(url.toLocalFile())
                    elif url_str.startswith(('http://', 'https://')):
                        items_to_process.append(url_str)

            if not items_to_process and mime_data.hasImage():
                qimage = clipboard.image()
                if not qimage.isNull():
                    temp_path = os.path.join(tempfile.gettempdir(), f"clip_{int(time.time()*1000)}.png")
                    qimage.save(temp_path, "PNG")
                    items_to_process.append(temp_path)

            if not items_to_process:
                if self.main_controller:
                    self.main_controller.error_occurred.emit(tr("msg.no_image_in_clipboard", self.store.settings.current_language))
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
                        if content_type and content_type.startswith('image/'):
                            temp_dir = tempfile.gettempdir()
                            timestamp = int(time.time() * 1000)
                            ext = (content_type.split('/')[-1] or 'png').lower()
                            if ext == 'jpeg':
                                ext = 'jpg'
                            temp_filename = f"url_image_{os.getpid()}_{timestamp}.{ext}"
                            image_path = os.path.join(temp_dir, temp_filename)
                            with open(image_path, 'wb') as f:
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
            from toolkit.widgets.paste_direction_overlay import PasteDirectionOverlay
            main_window = None
            if self.main_controller and hasattr(self.main_controller, 'presenter') and self.main_controller.presenter:
                main_window = self.main_controller.presenter.main_window_app
            if not main_window:
                return False

            overlay = PasteDirectionOverlay(
                main_window,
                main_window.ui.image_label,
                is_horizontal=self.store.viewport.is_horizontal
            )
            overlay.set_language(self.store.settings.current_language)
            self._paste_dialog = overlay

            def on_direction_selected(direction: str):
                slot_number = 1 if direction in ("up", "left") else 2

                local_files = [i for i in items_to_process if os.path.exists(i)]
                urls = [i for i in items_to_process if i.startswith('http')]

                if local_files:
                    if self.main_controller and self.main_controller.session_ctrl:
                        self.main_controller.session_ctrl.load_images_from_paths(local_files, slot_number)

                if urls:
                    if self.main_controller:
                        self.main_controller.error_occurred.emit(tr("msg.loading_images_from_clipboard", self.store.settings.current_language))
                    worker = GenericWorker(self.download_images_from_urls, urls, 15)

                    if self.main_controller and self.main_controller.session_ctrl:
                        worker.signals.result.connect(lambda paths: self.main_controller.session_ctrl.load_images_from_paths(paths, slot_number) if self.main_controller and self.main_controller.session_ctrl else None)
                        self.main_controller.thread_pool.start(worker)

            overlay.direction_selected.connect(on_direction_selected)
            overlay.show()
        except Exception as e:
            logger.error(f"Overlay error: {e}")

