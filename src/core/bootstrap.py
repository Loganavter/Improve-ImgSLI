import logging
import os
from typing import Optional

from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication

from core.plugin_coordinator import PluginCoordinator
from core.session_manager import SessionManager
from core.plugin_system import EventBus, PluginRegistry
from core.plugin_system.ui_integration import PluginUIRegistry
from core.store import Store
from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
from plugins.settings.manager import SettingsManager
from services.system.notifications import NotificationService
from shared_toolkit.core import setup_logging
from shared_toolkit.ui.managers.ui_resource_manager import UIResourceManager
from shared_toolkit.ui.managers.theme_manager import ThemeManager
from ui.main_window_composer import MainWindowComposer

logger = logging.getLogger("ImproveImgSLI")

class ApplicationContext:
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.store: Optional[Store] = None
        self.bridge = None
        self.settings_manager: Optional[SettingsManager] = None
        self.theme_manager: Optional[ThemeManager] = None
        self.notification_service: Optional[NotificationService] = None
        self.thread_pool: Optional[QThreadPool] = None
        self.event_bus: Optional[EventBus] = None
        self.plugin_registry: Optional[PluginRegistry] = None
        self.plugin_ui_registry: Optional[PluginUIRegistry] = None
        self.plugin_coordinator: Optional[PluginCoordinator] = None
        self.session_manager: Optional[SessionManager] = None
        self.ui_resource_manager: Optional[UIResourceManager] = None
        self._initialized = False
        self._is_shutting_down = False

    def initialize(self):
        if self._initialized:
            return

        self._build_core_services()
        self._load_persistent_state()
        self._configure_logging()
        self._configure_theme_manager()
        self._build_runtime_services()
        self._initialize_plugins()

        self._initialized = True
        logger.debug("ApplicationContext initialized")

    def _build_core_services(self):
        self.store = Store()

        from core.state_management.dispatcher import Dispatcher

        dispatcher = Dispatcher(self.store)
        self.store.set_dispatcher(dispatcher)

        from ui.store_bridge import QtStoreBridge

        self.bridge = QtStoreBridge(self.store)
        self.event_bus = EventBus()
        self.plugin_ui_registry = PluginUIRegistry()
        self.notification_service = NotificationService()
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)

    def _load_persistent_state(self):
        self.settings_manager = SettingsManager("improve-imgsli", "improve-imgsli")
        self.settings_manager.load_all_settings(self.store)
        if self.notification_service is not None:
            self.notification_service.set_enabled(
                getattr(self.store.settings, "system_notifications_enabled", True)
            )

    def _configure_logging(self):
        effective_debug = self.debug_mode or getattr(
            self.store.settings, "debug_mode_enabled", False
        )
        setup_logging("ImproveImgSLI", effective_debug, "IMPROVE_DEBUG")

        if os.getenv("IMPROVE_DEBUG", "0") == "1":
            self.store.settings.debug_mode_enabled = True

    def _configure_theme_manager(self):
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)

        for qss_path in (
            self._resource_path("shared_toolkit/ui/resources/styles/base.qss"),
            self._resource_path("shared_toolkit/ui/resources/styles/widgets.qss"),
            self._resource_path("resources/styles/app.qss"),
        ):
            self.theme_manager.register_qss_path(qss_path)

    def _build_runtime_services(self):
        self.plugin_registry = PluginRegistry(self)

    def _initialize_plugins(self):
        discovered_plugins = self.plugin_registry.discover_plugins()
        for plugin in discovered_plugins:
            for qss_path in plugin.get_qss_paths():
                self.theme_manager.register_qss_path(qss_path)

        self.plugin_coordinator = PluginCoordinator(self.event_bus)
        self.plugin_coordinator.register_plugins(discovered_plugins)
        self.plugin_coordinator.initialize(self)
        self.session_manager = SessionManager(self.store, self.plugin_coordinator)

    def _resource_path(self, relative_path: str) -> str:
        from utils.resource_loader import resource_path

        return resource_path(relative_path)

    def create_window_dependent_components(self, window):
        if not self._initialized:
            raise RuntimeError("ApplicationContext not initialized")
        composer = MainWindowComposer(self)
        components = composer.compose(window)
        self.ui_resource_manager = components.ui_resource_manager
        return {
            "geometry_manager": components.geometry_manager,
            "tray_manager": components.tray_manager,
            "main_controller": components.main_controller,
            "event_handler": components.event_handler,
            "presenter": components.presenter,
            "ui_resource_manager": components.ui_resource_manager,
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
                logger.warning(
                    "Некоторые потоки не завершились вовремя, принудительная очистка"
                )
                self.thread_pool.clear()

        if self.notification_service:
            try:
                self.notification_service.shutdown()
            except Exception as e:
                logger.error(f"Ошибка при остановке NotificationService: {e}")

        if self.ui_resource_manager:
            try:
                self.ui_resource_manager.shutdown()
            except Exception as e:
                logger.error(f"Ошибка при остановке UIResourceManager: {e}")

        logger.debug("ApplicationContext завершен")
