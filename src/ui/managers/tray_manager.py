

import logging
import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from utils.resource_loader import resource_path
from resources.translations import tr

logger = logging.getLogger("ImproveImgSLI")

class TrayManager(QObject):

    toggle_visibility_requested = pyqtSignal()
    open_last_file_requested = pyqtSignal()
    open_last_folder_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None, app_name: str = "Improve-ImgSLI", current_language: str = "en"):
        super().__init__(parent)
        self.app_name = app_name
        self.current_language = current_language
        self.tray_icon: QSystemTrayIcon = None
        self._last_saved_path: str = ""
        self._actions = {}

        self._create_tray_icon()

    def _create_tray_icon(self):
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                logger.warning("Системный трей недоступен.")
                return

            icon_path = resource_path("resources/icons/icon.png")
            icon = QIcon(icon_path)
            if icon.isNull():
                logger.warning(f"Не удалось загрузить иконку трея из {icon_path}")
                icon = QIcon.fromTheme("application", QIcon())

            self.tray_icon = QSystemTrayIcon(icon)
            self.tray_icon.setToolTip(self.app_name)

            self._build_context_menu()
            self.tray_icon.activated.connect(self._on_tray_activated)
            self.tray_icon.messageClicked.connect(self._on_tray_message_clicked)

            if not self.tray_icon.icon().isNull():
                self.tray_icon.show()
                logger.debug("Иконка трея создана и отображена.")
        except Exception as e:
            logger.error(f"Ошибка при создании иконки трея: {e}")
            self.tray_icon = None

    def _build_context_menu(self):
        if self.tray_icon is None:
            return

        tray_menu = QMenu()

        self._actions["toggle"] = QAction(tr("ui.showhide_window", self.current_language))
        self._actions["open_file"] = QAction(tr("action.open_last_file", self.current_language))
        self._actions["open_folder"] = QAction(tr("action.open_save_folder", self.current_language))
        self._actions["quit"] = QAction(tr("action.quit", self.current_language))

        self._actions["toggle"].triggered.connect(self.toggle_visibility_requested.emit)
        self._actions["open_file"].triggered.connect(self.open_last_file_requested.emit)
        self._actions["open_folder"].triggered.connect(self.open_last_folder_requested.emit)
        self._actions["quit"].triggered.connect(self.quit_requested.emit)

        self._actions["open_file"].setVisible(False)

        tray_menu.addAction(self._actions["toggle"])
        tray_menu.addSeparator()
        tray_menu.addAction(self._actions["open_file"])
        tray_menu.addAction(self._actions["open_folder"])
        tray_menu.addSeparator()
        tray_menu.addAction(self._actions["quit"])

        self.tray_icon.setContextMenu(tray_menu)

    def set_last_saved_path(self, path: str):
        self._last_saved_path = path
        if self._actions.get("open_file"):
            visible = bool(path and os.path.isfile(path))
            self._actions["open_file"].setVisible(visible)

    def get_last_saved_path(self) -> str:
        return self._last_saved_path

    def update_language(self, lang_code: str):
        self.current_language = lang_code
        if self._actions:
            self._actions["toggle"].setText(tr("ui.showhide_window", self.current_language))
            self._actions["open_file"].setText(tr("action.open_last_file", self.current_language))
            self._actions["open_folder"].setText(tr("action.open_save_folder", self.current_language))
            self._actions["quit"].setText(tr("action.quit", self.current_language))

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_visibility_requested.emit()

    def _on_tray_message_clicked(self):
        self.open_last_folder_requested.emit()

    def show_tray_notification(self, title: str, message: str, timeout_ms: int = 4000):
        if self.tray_icon and self.tray_icon.isVisible():
            try:
                self.tray_icon.showMessage(
                    title,
                    message,
                    QSystemTrayIcon.MessageIcon.Information,
                    max(0, int(timeout_ms))
                )
            except Exception as e:
                logger.error(f"Ошибка при показе уведомления трея: {e}")

    def shutdown(self):
        if self.tray_icon:
            try:
                self.tray_icon.hide()
                self.tray_icon.setContextMenu(None)
                self.tray_icon.deleteLater()
            except Exception:
                pass
            self.tray_icon = None
