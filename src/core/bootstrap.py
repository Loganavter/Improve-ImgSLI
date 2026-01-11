import logging
import os
from typing import Optional

from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication

from shared_toolkit.core import setup_logging
from core.store import Store
from core.constants import AppConstants
from utils.geometry import GeometryManager
from core.main_controller import MainController
from core.plugin_coordinator import PluginCoordinator
from plugins.settings.manager import SettingsManager
from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
from events.app_event_handler import EventHandler
from services.system.notifications import NotificationService
from toolkit.managers.theme_manager import ThemeManager
from ui.managers.tray_manager import TrayManager
from ui.presenters.main_window_presenter import MainWindowPresenter
from toolkit.widgets.composite.toast import ToastManager
from core.plugin_system import PluginRegistry, EventBus
from core.plugin_system.ui_integration import PluginUIRegistry

logger = logging.getLogger("ImproveImgSLI")

class ApplicationContext:
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.store: Optional[Store] = None
        self.settings_manager: Optional[SettingsManager] = None
        self.theme_manager: Optional[ThemeManager] = None
        self.notification_service: Optional[NotificationService] = None
        self.thread_pool: Optional[QThreadPool] = None
        self.event_bus: Optional[EventBus] = None
        self.plugin_registry: Optional[PluginRegistry] = None
        self.plugin_ui_registry: Optional[PluginUIRegistry] = None
        self.plugin_coordinator: Optional[PluginCoordinator] = None
        self._initialized = False
        self._is_shutting_down = False

    def initialize(self):
        if self._initialized:
            return

        self.store = Store()

        from core.state_management.dispatcher import Dispatcher
        dispatcher = Dispatcher(self.store)
        self.store.set_dispatcher(dispatcher)

        setup_logging("ImproveImgSLI", self.debug_mode, "IMPROVE_DEBUG")

        self.settings_manager = SettingsManager("improve-imgsli", "improve-imgsli")
        self.settings_manager.load_all_settings(self.store)

        if os.getenv("IMPROVE_DEBUG", "0") == "1":
            self.store.settings.debug_mode_enabled = True

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)

        app_qss = self._resource_path("resources/styles/app.qss")
        self.theme_manager.register_qss_path(app_qss)

        toolkit_qss = self._resource_path("toolkit/resources/styles/widgets.qss")
        self.theme_manager.register_qss_path(toolkit_qss)

        video_editor_qss = self._resource_path("plugins/video_editor/resources/editor.qss")
        self.theme_manager.register_qss_path(video_editor_qss)

        self.notification_service = NotificationService()

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)

        self.event_bus = EventBus()
        self.plugin_ui_registry = PluginUIRegistry()
        self.plugin_registry = PluginRegistry(self)
        discovered_plugins = self.plugin_registry.discover_plugins()

        self.plugin_coordinator = PluginCoordinator(self.event_bus)
        self.plugin_coordinator.register_plugins(discovered_plugins)
        self.plugin_coordinator.initialize(self)

        self._initialized = True
        logger.debug("ApplicationContext initialized")

    def _resource_path(self, relative_path: str) -> str:
        from utils.resource_loader import resource_path
        return resource_path(relative_path)

    def create_window_dependent_components(self, window):
        if not self._initialized:
            raise RuntimeError("ApplicationContext not initialized")

        geometry_manager = GeometryManager(window, self.settings_manager.settings, self.store)

        from events.drag_drop_handler import DragAndDropService
        if DragAndDropService._instance is None:
            DragAndDropService._instance = DragAndDropService(self.store, window)

        tray_manager = TrayManager(window, current_language=self.store.settings.current_language)
        tray_manager.toggle_visibility_requested.connect(window._toggle_main_window_visibility)
        tray_manager.open_last_file_requested.connect(window._open_last_saved_file)
        tray_manager.open_last_folder_requested.connect(window._open_last_saved_folder)
        tray_manager.quit_requested.connect(QApplication.instance().quit)

        main_controller = MainController(self)

        event_handler = EventHandler(self.store, None)

        presenter = MainWindowPresenter(
            window,
            window.ui,
            self.store,
            main_controller,
            plugin_ui_registry=self.plugin_ui_registry,
        )
        event_handler.presenter = presenter
        main_controller.set_presenter(presenter)
        presenter.connect_event_handler_signals(event_handler)

        toast_manager = ToastManager(window, window.ui.image_label)

        self.notification_service.set_tray_icon(tray_manager.tray_icon)

        return {
            "geometry_manager": geometry_manager,
            "tray_manager": tray_manager,
            "main_controller": main_controller,
            "event_handler": event_handler,
            "presenter": presenter,
            "toast_manager": toast_manager,
        }

    def apply_theme_to_app(self, app: QApplication):
        self.theme_manager.apply_theme_to_app(app)
        self.theme_manager.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self):
        pass

    def shutdown(self):
        self._is_shutting_down = True
        logger.debug("Начало завершения работы ApplicationContext...")

        if self.plugin_coordinator and self.plugin_coordinator.lifecycle:
            try:
                self.plugin_coordinator.lifecycle.shutdown_all()
            except Exception as e:
                logger.error(f"Ошибка при остановке плагинов: {e}")

        if self.thread_pool:
            self.thread_pool.clear()
            if not self.thread_pool.waitForDone(2000):
                logger.warning("Некоторые потоки не завершились вовремя, принудительная очистка")
                self.thread_pool.clear()

        if self.notification_service:
            try:
                self.notification_service.shutdown()
            except Exception as e:
                logger.error(f"Ошибка при остановке NotificationService: {e}")

        logger.debug("ApplicationContext завершен")
