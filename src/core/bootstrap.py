import logging
import os
from typing import Optional

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from core.plugin_coordinator import PluginCoordinator
from core.runtime_flags import RuntimeFlags
from core.session_manager import SessionManager
from core.plugin_system import EventBus, PluginDefinitionRegistry, PluginRegistry
from core.plugin_system.ui_integration import PluginUIRegistry
from core.store import Store
from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
from plugins.settings.manager import SettingsManager
from services.system.notifications import NotificationService
from sli_ui_toolkit.core import setup_logging
from sli_ui_toolkit.widgets import install_application_tooltips
from shared_toolkit.ui.managers.ui_resource_manager import UIResourceManager
from sli_ui_toolkit.theme import ThemeManager
from ui.main_window.composer import MainWindowComposer

logger = logging.getLogger("ImproveImgSLI")

class ApplicationContext:
    def __init__(
        self,
        debug_mode: bool = False,
        runtime_flags: RuntimeFlags | None = None,
    ):
        self.runtime_flags = runtime_flags or RuntimeFlags(debug=debug_mode)
        self.debug_mode = self.runtime_flags.debug
        self.store: Optional[Store] = None
        self.bridge = None
        self.settings_manager: Optional[SettingsManager] = None
        self.theme_manager: Optional[ThemeManager] = None
        self.notification_service: Optional[NotificationService] = None
        self.thread_pool: Optional[QThreadPool] = None
        self.event_bus: Optional[EventBus] = None
        self.plugin_registry: Optional[PluginRegistry] = None
        self.plugin_definition_registry: Optional[PluginDefinitionRegistry] = None
        self.plugin_ui_registry: Optional[PluginUIRegistry] = None
        self.plugin_coordinator: Optional[PluginCoordinator] = None
        self.session_manager: Optional[SessionManager] = None
        self.ui_resource_manager: Optional[UIResourceManager] = None
        self._initialized = False
        self._is_shutting_down = False

    def initialize(self):
        if self._initialized:
            return

        self._maybe_install_tracer()
        self._build_core_services()
        self._load_persistent_state()
        self._configure_logging()
        self._configure_theme_manager()
        self._build_runtime_services()
        self._initialize_plugins()
        self._load_canvas_feature_settings()

        self._initialized = True
        logger.debug("ApplicationContext initialized")

    def _maybe_install_tracer(self):
        from core.tracing.tracer import is_trace_env_enabled
        if not (self.debug_mode or is_trace_env_enabled()):
            return
        try:
            from core.tracing.instrumentation import install_instrumentation
            install_instrumentation()
        except Exception as exc:
            logger.warning("tracer install failed: %s", exc, exc_info=True)
            return
        try:
            from core.tracing.file_sink import install_file_sink
            install_file_sink()
        except Exception as exc:
            logger.warning("tracer file sink install failed: %s", exc, exc_info=True)

    def _load_canvas_feature_settings(self):
        self.settings_manager._load_canvas_feature_settings(self.store.viewport)

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
            from core.state_management.actions import SetDebugModeEnabledAction
            self.store.get_dispatcher().dispatch(SetDebugModeEnabledAction(True))

    def _configure_theme_manager(self):
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)

        # Resolve the saved theme now, before any icons get fetched (e.g. the
        # title bar built in MainWindow.__init__). ThemeManager defaults to
        # "light" until set_theme() is called; icons resolved against that
        # default get cached forever in IconService and never refreshed, so
        # is_dark() must already be correct by the time UI construction
        # starts. lifecycle.py's ApplyThemeStep re-applies the same value
        # later (to also push QSS/palette onto the QApplication instance),
        # this call only needs to fix is_dark() early.
        theme_from_env = os.getenv("APP_THEME", "auto").lower()
        initial_theme = (
            theme_from_env if theme_from_env != "auto" else self.store.settings.theme
        )
        self.theme_manager.set_theme(initial_theme)

        for qss_path in (
            self._resource_path("shared_toolkit/ui/resources/styles/base.qss"),
            self._resource_path("shared_toolkit/ui/resources/styles/widgets.qss"),
            self._resource_path("resources/styles/app.qss"),
        ):
            self.theme_manager.register_qss_path(qss_path)

    def _build_runtime_services(self):
        self.plugin_registry = PluginRegistry(self)
        self.plugin_definition_registry = PluginDefinitionRegistry()

    def _initialize_plugins(self):
        discovered_plugins = self.plugin_registry.discover_plugins()
        self.plugin_definition_registry.register_plugins(discovered_plugins)
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
        components = MainWindowComposer(self).compose(window)
        self.ui_resource_manager = components.ui_resource_manager
        return components

    def apply_theme_to_app(self, app: QApplication):
        install_application_tooltips(app)
        from shared_toolkit.ui.decorate_dialog import install_application_dialog_decorations
        install_application_dialog_decorations(app)
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
