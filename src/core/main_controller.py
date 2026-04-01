import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

from core.events import (
    ComparisonUIUpdateEvent,
    CoreErrorOccurredEvent,
    CoreUpdateRequestedEvent,
)
from core.main_controller_parts import (
    VideoExportActions,
    ViewportActions,
    WorkspaceSessionActions,
)

if TYPE_CHECKING:
    from core.bootstrap import ApplicationContext

logger = logging.getLogger("ImproveImgSLI")

class MainController(QObject):

    error_occurred = pyqtSignal(str)
    update_requested = pyqtSignal()
    ui_update_requested = pyqtSignal(list)
    start_interactive_movement = pyqtSignal()
    stop_interactive_movement = pyqtSignal()

    video_export_progress = pyqtSignal(int)
    video_export_finished = pyqtSignal(bool)
    video_export_log = pyqtSignal(str)

    def __init__(self, context: "ApplicationContext"):
        super().__init__()
        self.context = context
        self.store = context.store
        self.thread_pool = context.thread_pool
        self.settings_manager = context.settings_manager
        self.event_bus = context.event_bus
        self.session_manager = context.session_manager
        self.window_shell = None
        self._session_controller = None
        self._settings_controller = None
        self._export_controller = None
        self._analysis_controller = None
        self._metrics_service = None
        self._magnifier_plugin = None
        self._viewport_controller = None
        self._layout_plugin = None
        self._recorder = None
        self._video_exporter = None
        self._clipboard_service = None

        self.workspace = WorkspaceSessionActions(self)
        self.viewport = ViewportActions(self)
        self.video_export = VideoExportActions(self)
        self.refresh_runtime_bindings()

        if self.event_bus:

            self.event_bus.subscribe(
                CoreUpdateRequestedEvent, self._on_core_update_requested
            )
            self.event_bus.subscribe(
                CoreErrorOccurredEvent, self._on_core_error_occurred
            )
            self.event_bus.subscribe(
                ComparisonUIUpdateEvent, self._on_comparison_ui_update
            )

    def _on_core_update_requested(self, event: CoreUpdateRequestedEvent):
        self.update_requested.emit()

    def _on_core_error_occurred(self, event: CoreErrorOccurredEvent):
        self.error_occurred.emit(event.error)

    def _on_comparison_ui_update(self, event: ComparisonUIUpdateEvent):

        self.ui_update_requested.emit(list(event.components))

    def _get_plugin(self, name: str):
        coordinator = getattr(self.context, "plugin_coordinator", None)
        return coordinator.get_plugin(name) if coordinator is not None else None

    def execute_plugin_command(self, plugin_name: str, command: str, *args, **kwargs):
        coordinator = getattr(self.context, "plugin_coordinator", None)
        if coordinator is None:
            raise RuntimeError("Plugin coordinator is not available")
        return coordinator.execute_command(plugin_name, command, *args, **kwargs)

    def refresh_runtime_bindings(self):
        comparison_plugin = self._get_plugin("comparison")
        self._session_controller = (
            getattr(comparison_plugin, "session_ctrl", None)
            if comparison_plugin is not None
            else None
        )

        settings_plugin = self._get_plugin("settings")
        self._settings_controller = (
            settings_plugin.get_controller()
            if settings_plugin is not None and hasattr(settings_plugin, "get_controller")
            else None
        )

        export_plugin = self._get_plugin("export")
        self._export_controller = (
            export_plugin.get_controller()
            if export_plugin is not None and hasattr(export_plugin, "get_controller")
            else None
        )
        self._recorder = getattr(export_plugin, "recorder", None) if export_plugin else None
        self._video_exporter = (
            getattr(export_plugin, "video_exporter", None) if export_plugin else None
        )
        self._clipboard_service = (
            getattr(export_plugin, "clipboard_service", None) if export_plugin else None
        )

        analysis_plugin = self._get_plugin("analysis")
        self._analysis_controller = (
            analysis_plugin.get_controller()
            if analysis_plugin is not None and hasattr(analysis_plugin, "get_controller")
            else None
        )
        self._metrics_service = (
            getattr(analysis_plugin, "metrics_service", None)
            if analysis_plugin is not None
            else None
        )

        self._magnifier_plugin = self._get_plugin("magnifier")

        viewport_plugin = self._get_plugin("viewport")
        self._viewport_controller = (
            viewport_plugin.get_controller()
            if viewport_plugin is not None and hasattr(viewport_plugin, "get_controller")
            else None
        )

        self._layout_plugin = self._get_plugin("layout")

    @property
    def sessions(self):
        return self._session_controller

    @property
    def settings(self):
        return self._settings_controller

    @property
    def exporting(self):
        return self._export_controller

    @property
    def recorder(self):
        return self._recorder

    @property
    def video_exporter(self):
        return self._video_exporter

    @property
    def clipboard_service(self):
        return self._clipboard_service

    @property
    def analysis(self):
        return self._analysis_controller

    @property
    def metrics_service(self):
        return self._metrics_service

    @property
    def magnifier(self):
        return self._magnifier_plugin

    @property
    def viewport_plugin(self):
        return self._viewport_controller

    @property
    def layout(self):
        return self._layout_plugin

    def attach_window_shell(self, window_shell):
        self.window_shell = window_shell
        self.refresh_runtime_bindings()
        for plugin_name in ("comparison", "export", "settings"):
            plugin = self._get_plugin(plugin_name)
            if plugin is None:
                continue
            configurator = getattr(plugin, "configure_controller", None)
            if callable(configurator):
                presenter = (
                    window_shell.get_feature(plugin_name)
                    if hasattr(window_shell, "get_feature")
                    else window_shell
                )
                configurator(self, presenter)
                self.refresh_runtime_bindings()
            binder = getattr(plugin, "bind_window_shell", None)
            if callable(binder):
                binder(window_shell)
        self.refresh_runtime_bindings()
