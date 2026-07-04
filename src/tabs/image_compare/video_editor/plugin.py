from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import (
    IControllablePlugin,
    IServicePlugin,
    ISessionPlugin,
    IVideoTrackProvider,
)
from core.session_blueprints import (
    SessionBlueprint,
    SessionResourceBlueprint,
    SessionSlotBlueprint,
)
from plugins.export.events import (
    ExportOpenVideoEditorEvent,
    ExportTogglePauseRecordingEvent,
    ExportToggleRecordingEvent,
)
from plugins.settings.events import SettingsChangeLanguageEvent
from tabs.image_compare.video_editor.controller import VideoEditorController
from tabs.image_compare.video_editor.dialog import VideoEditorDialog
from tabs.image_compare.video_editor.model import VideoSelectionState, VideoTimelineState
from tabs.image_compare.video_editor.services.export import VideoExporterService
from tabs.image_compare.video_editor.services.recorder import Recorder

logger = logging.getLogger("ImproveImgSLI")


@plugin(name="video_editor", version="1.0")
class VideoEditorPlugin(Plugin, IControllablePlugin, IServicePlugin, ISessionPlugin):
    capabilities = ("recording",)

    def __init__(self):
        super().__init__()
        self._editor_dialog: VideoEditorDialog | None = None
        self.recorder: Recorder | None = None
        self.video_exporter: VideoExporterService | None = None
        self.controller: VideoEditorController | None = None
        self.plugin_coordinator: Any | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.event_bus = getattr(context, "event_bus", None)
        self.thread_pool = getattr(context, "thread_pool", None)
        self.store = getattr(context, "store", None)
        self.plugin_coordinator = getattr(context, "plugin_coordinator", None)
        if self.event_bus is not None:
            self.event_bus.subscribe(
                SettingsChangeLanguageEvent, self._on_language_changed
            )

    def configure_controller(
        self,
        main_controller: Any | None = None,
        presenter: Any | None = None,
    ) -> None:
        if self.controller is not None:
            return
        extra_adapters = self._collect_video_keyframe_adapters()
        # `window_shell.get_feature("video_editor")` has no mapping entry (it only
        # knows "image_canvas"/"toolbar"/"export"/"settings"), so `presenter` here
        # is always None. The real GpuExportService lives on the export plugin's
        # presenter, reachable via window_shell.get_feature("export").
        window_shell = getattr(main_controller, "window_shell", None)
        export_presenter = (
            window_shell.get_feature("export")
            if window_shell is not None and hasattr(window_shell, "get_feature")
            else None
        )
        gpu_export_service = getattr(export_presenter, "gpu_export_service", None)
        self.recorder = Recorder(self.store, extra_adapters=extra_adapters)
        self.video_exporter = VideoExporterService(
            self.recorder,
            self.store,
            main_controller,
            gpu_export_service=gpu_export_service,
        )
        self.controller = VideoEditorController(
            store=self.store,
            thread_pool=self.thread_pool,
            recorder=self.recorder,
            video_exporter=self.video_exporter,
            video_editor_plugin=self,
            presenter=presenter,
            main_controller=main_controller,
            event_bus=self.event_bus,
        )

        if self.event_bus is not None:
            self.event_bus.subscribe(
                ExportToggleRecordingEvent, self.controller.on_toggle_recording
            )
            self.event_bus.subscribe(
                ExportTogglePauseRecordingEvent,
                self.controller.on_toggle_pause_recording,
            )
            self.event_bus.subscribe(
                ExportOpenVideoEditorEvent, self.controller.on_open_video_editor
            )

    def bind_window_shell(self, window_shell: Any) -> None:
        if self.controller is None:
            return
        if hasattr(window_shell, "get_feature"):
            presenter = window_shell.get_feature("export")
        else:
            presenter = window_shell
        if presenter is not None:
            self.controller.presenter = presenter

    def get_controller(self) -> VideoEditorController | None:
        return self.controller

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        if self.controller and hasattr(self.controller, command):
            return getattr(self.controller, command)(*args, **kwargs)
        raise AttributeError(f"video_editor plugin has no command '{command}'")

    def get_service(self) -> Any:
        return self.recorder

    def provides_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def _collect_video_keyframe_adapters(self) -> tuple[Any, ...]:
        if self.plugin_coordinator is None:
            return ()
        adapters: list[Any] = []
        for other in self.plugin_coordinator.iter_plugins():
            if other is self:
                continue
            if isinstance(other, IVideoTrackProvider):
                adapters.extend(other.get_video_keyframe_adapters())
        return tuple(adapters)

    def get_qss_paths(self) -> tuple[str, ...]:
        return (self.plugin_resource_path("resources", "editor.qss"),)

    def open_editor(
        self, snapshots: list[Any], export_controller: Any, main_window_app: Any
    ) -> None:
        if not snapshots or not export_controller:
            logger.warning(
                "VideoEditorPlugin.open_editor: snapshots or export_controller is None"
            )
            return

        try:
            if self._editor_dialog is not None:
                try:
                    if self._editor_dialog.isMinimized():
                        self._editor_dialog.showNormal()
                    self._editor_dialog.show()
                    self._editor_dialog.raise_()
                    self._editor_dialog.activateWindow()
                    return
                except RuntimeError:
                    self._editor_dialog = None

            dialog = VideoEditorDialog(
                snapshots,
                export_controller,
                main_window_app,
                parent=None,
            )
            self._editor_dialog = dialog
            dialog.destroyed.connect(self._forget_editor)
            dialog.readyToShow.connect(self._show_editor_dialog)
            dialog.show()
        except Exception as e:
            logger.exception(
                f"VideoEditorPlugin.open_editor: Error creating/showing dialog: {e}"
            )
            raise

    def _show_editor_dialog(self) -> None:
        dialog = self._editor_dialog
        if dialog is None:
            return
        try:
            if dialog.isMinimized():
                dialog.showNormal()
            dialog.show()
            if self._can_activate_deferred_dialog(dialog):
                dialog.raise_()
                dialog.activateWindow()
        except RuntimeError:
            self._editor_dialog = None

    @staticmethod
    def _can_activate_deferred_dialog(dialog) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        if app.applicationState() != Qt.ApplicationState.ApplicationActive:
            return False
        active_window = app.activeWindow()
        return active_window is None or active_window is dialog

    def _forget_editor(self, *_args) -> None:
        self._editor_dialog = None

    def _on_language_changed(self, event: SettingsChangeLanguageEvent) -> None:
        if self._editor_dialog is not None:
            self._editor_dialog.update_language(event.lang_code)

    def get_ui_components(self) -> dict[str, Any]:
        return {}

    def get_session_blueprints(self) -> tuple[SessionBlueprint, ...]:
        return ()

    def shutdown(self) -> None:
        super().shutdown()
        if self.video_exporter is not None:
            try:
                self.video_exporter.cleanup()
            except Exception as e:
                logger.error(f"VideoExporterService cleanup failed: {e}")
