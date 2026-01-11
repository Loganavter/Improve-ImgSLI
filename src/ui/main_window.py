import logging
import os
from pathlib import Path

import PIL.Image
from PyQt6.QtCore import (
    QEvent,
    Qt,
    QTimer,
    QUrl,
    QSize,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QResizeEvent,
)
from PyQt6.QtWidgets import QApplication, QWidget

from core.bootstrap import ApplicationContext
from utils.geometry import GeometryManager
from core.main_controller import MainController
from ui.main_window_ui import Ui_ImageComparisonApp
from ui.presenters.main_window_presenter import MainWindowPresenter
from utils.resource_loader import resource_path
from toolkit.managers.font_manager import FontManager

try:
    from desktop_notifier import Attachment, DesktopNotifier, Icon, Urgency
except Exception:
    DesktopNotifier = None
    Icon = None
    Attachment = None
    Urgency = None

try:
    from plugins.settings.dialog import SettingsDialog
    _SETTINGS_DIALOG_AVAILABLE = True
except ImportError:
    logging.getLogger("ImproveImgSLI").warning("settings_dialog.py not found.")
    _SETTINGS_DIALOG_AVAILABLE = False

try:
    from ui.onboarding import OnboardingOverlay
    _ONBOARDING_OVERLAY_AVAILABLE = True
except ImportError:
    logging.getLogger("ImproveImgSLI").warning("onboarding.py not found.")
    _ONBOARDING_OVERLAY_AVAILABLE = False

from resources.translations import tr

PIL.Image.MAX_IMAGE_PIXELS = None
logger = logging.getLogger("ImproveImgSLI")

from services.system.notifications import NotificationService
from ui.managers.tray_manager import TrayManager

class MainWindow(QWidget):
    def __init__(self, parent=None, debug_mode: bool = False):
        super().__init__(parent)
        self.setObjectName("ImageComparisonApp")

        self._is_ui_stable = False
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))

        self.app_context = ApplicationContext(debug_mode)
        self.app_context.initialize()

        self.store = self.app_context.store
        self.settings_manager = self.app_context.settings_manager
        self.theme_manager = self.app_context.theme_manager
        self.notification_service = self.app_context.notification_service
        self.thread_pool = self.app_context.thread_pool

        app = QApplication.instance()
        if app:
            self.theme_manager.apply_theme_to_app(app)
            self.theme_manager.theme_changed.connect(self._on_theme_changed)

        self.ui = Ui_ImageComparisonApp()
        self.ui.setupUi(self)

        self.ui.install_rating_wheel_handlers()

        try:
            self.font_path_absolute = FontManager.get_instance().get_font_path_for_image_text(self.store)
        except Exception:
            self.font_path_absolute = None

        components = self.app_context.create_window_dependent_components(self)

        self.geometry_manager = components["geometry_manager"]
        self.tray_manager = components["tray_manager"]
        self.main_controller = components["main_controller"]
        self.event_handler = components["event_handler"]
        self.presenter = components["presenter"]
        self.toast_manager = components["toast_manager"]

        self.save_task_counter = 0

        self.setAcceptDrops(True)

        self._debounced_resize_timer = QTimer(self)
        self._debounced_resize_timer.setSingleShot(True)
        self._debounced_resize_timer.setInterval(150)
        self._debounced_resize_timer.timeout.connect(self._handle_debounced_resize)

        self.installEventFilter(self.event_handler)
        self.ui.image_label.installEventFilter(self.event_handler)
        QApplication.instance().installEventFilter(self.event_handler)

        QTimer.singleShot(0, self.initialize_application)

    def initialize_application(self):
        self.geometry_manager.load_and_apply()

        theme_from_env = os.getenv("APP_THEME", "auto").lower()
        final_theme_setting = theme_from_env if theme_from_env != "auto" else self.store.settings.theme
        self.apply_application_theme(final_theme_setting)

        try:
            FontManager.get_instance().apply_from_state(self.store)
        except Exception:
            pass

        self._update_image_label_background()

        if self.main_controller and self.main_controller.session_ctrl:
            self.main_controller.session_ctrl.initialize_app_display()

        self.ui.reapply_button_styles()

        if hasattr(self.ui, 'btn_magnifier_color_settings') and hasattr(self.ui.btn_magnifier_color_settings, 'button'):
            accent_color = QColor(self.theme_manager.get_color("accent"))
            accent_color.setAlpha(200)
            self.ui.btn_magnifier_color_settings.button.set_color(accent_color)

        if hasattr(self.ui, 'btn_magnifier_color_settings_beginner') and hasattr(self.ui.btn_magnifier_color_settings_beginner, 'button'):
            accent_color = QColor(self.theme_manager.get_color("accent"))
            accent_color.setAlpha(200)
            self.ui.btn_magnifier_color_settings_beginner.button.set_color(accent_color)

        if _ONBOARDING_OVERLAY_AVAILABLE and self.settings_manager.is_first_run():

            self.onboarding_overlay = OnboardingOverlay(self.settings_manager, self.store, self)

            self.onboarding_overlay.resize(self.size())
            self.onboarding_overlay.show()

            self.onboarding_overlay.completed.connect(self._on_onboarding_completed)

    def apply_application_theme(self, theme_name: str):
        app = QApplication.instance()
        self.theme_manager.set_theme(theme_name, app)
        if self.store.settings.theme != theme_name:
            self.store.settings.theme = theme_name
        self.ui.reapply_button_styles()

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:

            QTimer.singleShot(0, self.schedule_update)

    def _handle_debounced_resize(self):
        if self.store.viewport.resize_in_progress:
            self.store.viewport.resize_in_progress = False
            self.schedule_update()
        if not self.isMaximized() and not self.isFullScreen():
            self.geometry_manager.update_normal_geometry_if_needed()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)

        if hasattr(self, 'onboarding_overlay') and self.onboarding_overlay:
            self.onboarding_overlay.resize(self.size())

        if hasattr(self, 'presenter') and self.presenter:
            self.presenter.ui_manager.unified_flyout.hide()

        if not self.store.viewport.resize_in_progress:
            self.store.viewport.resize_in_progress = True

        self.ui.update_drag_overlays(
            self.store.viewport.is_horizontal,
            self.ui.drag_overlay1.isVisible()
        )
        self._debounced_resize_timer.start()

    def closeEvent(self, event: QEvent):
        logger.debug("Начало закрытия главного окна...")

        self._closing = True

        if hasattr(self, 'app_context') and self.app_context:
            self.app_context._is_shutting_down = True

        if hasattr(self, 'presenter') and self.presenter:

            if hasattr(self.presenter, 'export_presenter'):
                try:
                    self.presenter.export_presenter.cancel_all_exports()
                except Exception as e:
                    logger.error(f"Ошибка при отмене экспортов: {e}")

            if hasattr(self.presenter, 'image_canvas_presenter'):
                image_presenter = self.presenter.image_canvas_presenter
                if hasattr(image_presenter, '_update_scheduler_timer'):
                    image_presenter._update_scheduler_timer.stop()

        if hasattr(self, '_debounced_resize_timer'):
            self._debounced_resize_timer.stop()

        try:
            self.geometry_manager.update_normal_geometry_if_needed()
            self.geometry_manager.save_on_close()
            self.settings_manager.save_all_settings(self.store)
        except Exception as e:
            logger.error(f"Ошибка при сохранении настроек: {e}")

        if self.tray_manager:
            try:
                self.tray_manager.shutdown()
            except Exception as e:
                logger.error(f"Ошибка при остановке TrayManager: {e}")

        if hasattr(self, 'app_context') and self.app_context:
            try:
                self.app_context.shutdown()
            except Exception as e:
                logger.error(f"Ошибка при завершении ApplicationContext: {e}")

        logger.debug("Завершение закрытия главного окна")
        super().closeEvent(event)

    def moveEvent(self, event: QEvent):
        super().moveEvent(event)
        if hasattr(self, 'presenter') and self.presenter:
            self.presenter.ui_manager.unified_flyout.hide()
        if not self.isMaximized() and not self.isFullScreen():
            self.geometry_manager.update_normal_geometry_if_needed()

    def showEvent(self, event: QEvent):
        super().showEvent(event)
        if not self._is_ui_stable:
             QTimer.singleShot(50, lambda: setattr(self, '_is_ui_stable', True) or self.schedule_update())

    def mousePressEvent(self, event):

        focused = self.focusWidget()
        if focused in (self.ui.edit_name1, self.ui.edit_name2):
            focused.clearFocus()
        super().mousePressEvent(event)

    def schedule_update(self):
        if hasattr(self, 'presenter') and self.presenter and hasattr(self.presenter, 'image_canvas_presenter'):
            self.presenter.image_canvas_presenter.schedule_update()

    def _update_image_label_background(self):
        if hasattr(self.ui, "image_label"):
            bg = self.theme_manager.get_color("label.image.background")
            pal = self.ui.image_label.palette()
            pal.setColor(self.ui.image_label.backgroundRole(), bg)
            self.ui.image_label.setPalette(pal)

    def _on_theme_changed(self):
        self._update_image_label_background()

        try:

            FontManager.get_instance().apply_from_state(self.store)

            current_font = QApplication.font()
            family = current_font.family()

            self.setStyleSheet(f"QWidget {{ font-family: '{family}'; }}")

        except Exception as e:
            logger.error(f"Error enforcing font style: {e}")

        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def notify_system(self, title: str, message: str, image_path: str | None = None, timeout_ms: int = 4000):
        if getattr(self.store.settings, "system_notifications_enabled", True):
            self.notification_service.send(title, message, image_path, timeout_ms)

    def update_tray_actions_visibility(self):
        if self.tray_manager:
            path = getattr(self, "_last_saved_path", None)
            self.tray_manager.set_last_saved_path(path)

    def _toggle_main_window_visibility(self):
        if self.isVisible() and not self.isMinimized():
            self.showMinimized()
        else:
            self.show()
            self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
            self.raise_()
            self.activateWindow()

    def _open_last_saved_file(self):
        path = getattr(self, "_last_saved_path", None)
        if path and os.path.isfile(path):
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _open_last_saved_folder(self):
        path = getattr(self, "_last_saved_path", None)
        folder = os.path.dirname(path) if path else (self.store.settings.export_default_dir or os.path.expanduser("~"))
        if folder and os.path.isdir(folder):
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _on_onboarding_completed(self, mode_key: str):

        self.store.settings.ui_mode = mode_key
        if self.presenter and self.presenter.main_controller:

            layout_plugin = self.presenter.main_controller.plugin_coordinator.get_plugin("layout")
            if layout_plugin and layout_plugin.manager:
                layout_plugin.manager.apply_mode(mode_key)

            if self.presenter.main_controller.event_bus:
                from core.events import SettingsUIModeChangedEvent
                self.presenter.main_controller.event_bus.emit(SettingsUIModeChangedEvent(mode_key))

        if hasattr(self, 'onboarding_overlay') and self.onboarding_overlay:
            self.onboarding_overlay.hide()
            self.onboarding_overlay.deleteLater()
        self.onboarding_overlay = None
