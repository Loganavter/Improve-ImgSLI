from __future__ import annotations

import os

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices

class MainWindowActions:
    def __init__(self, window):
        self.window = window
        self._last_saved_path: str | None = None

    def notify_system(
        self,
        title: str,
        message: str,
        image_path: str | None = None,
        timeout_ms: int = 4000,
    ) -> None:
        window = self.window
        enabled = getattr(window.store.settings, "system_notifications_enabled", True)
        if not enabled:
            return
        try:
            window.notification_service.send(title, message, image_path, timeout_ms)
        except Exception:
            import logging

            logging.getLogger("ImproveImgSLI").exception("notify_system send failed")

    def set_last_saved_path(self, path: str | None) -> None:
        self._last_saved_path = path

    def update_tray_actions_visibility(self) -> None:
        window = self.window
        if window.tray_manager:
            window.tray_manager.set_last_saved_path(self._last_saved_path)

    def toggle_main_window_visibility(self) -> None:
        window = self.window
        if window.isVisible() and not window.isMinimized():
            window.showMinimized()
            return
        window.show()
        window.setWindowState(
            (window.windowState() & ~Qt.WindowState.WindowMinimized)
            | Qt.WindowState.WindowActive
        )
        window.raise_()
        window.activateWindow()

    def open_last_saved_file(self) -> None:
        path = self._last_saved_path
        if path and os.path.isfile(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_last_saved_folder(self) -> None:
        window = self.window
        path = self._last_saved_path
        folder = (
            os.path.dirname(path)
            if path
            else (window.store.settings.export_default_dir or os.path.expanduser("~"))
        )
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
