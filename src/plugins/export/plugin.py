from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QTimer

logger = logging.getLogger("ImproveImgSLI")

_GPU_WARM_UP_DELAY_MS = 3000

from core.events import WorkspaceSessionActivatedEvent
from plugins.export.events import (
    ExportOpenVideoEditorEvent,
    ExportPasteImageFromClipboardEvent,
    ExportTogglePauseRecordingEvent,
    ExportToggleRecordingEvent,
)
from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import (
    IControllablePlugin,
    IServicePlugin,
    IVideoTrackProvider,
)
from plugins.export.controller import ExportController

@plugin(name="export", version="1.0", startup_tier="deferred", startup_order=10)
class ExportPlugin(Plugin, IControllablePlugin, IServicePlugin):
    capabilities = ("export", "recording")

    def __init__(self):
        super().__init__()
        self.controller: ExportController | None = None
        self.recorder: Any | None = None
        self.video_exporter: Any | None = None
        self.clipboard_service: Any | None = None
        self.video_editor_plugin: Any | None = None
        self.thread_pool: Any | None = None
        self.event_bus: Any | None = None
        self.store: Any | None = None
        self.plugin_coordinator: Any | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.thread_pool = getattr(context, "thread_pool", None)
        self.event_bus = getattr(context, "event_bus", None)
        self.plugin_coordinator = getattr(context, "plugin_coordinator", None)
        self.video_editor_plugin = (
            self.plugin_coordinator.get_plugin("video_editor")
            if self.plugin_coordinator
            else None
        )

    def get_qss_paths(self) -> tuple[str, ...]:
        return (self.plugin_resource_path("resources", "export.qss"),)

    def configure_controller(
        self,
        main_controller: Any | None = None,
        presenter: Any | None = None,
    ) -> None:
        if self.controller:
            return
        extra_adapters = self._collect_video_keyframe_adapters()
        self.recorder, self.video_exporter = self._create_recording_services(
            main_controller=main_controller,
            presenter=presenter,
            extra_adapters=extra_adapters,
        )
        self.clipboard_service = self._create_clipboard_service(main_controller)
        self.controller = ExportController(
            store=self.store,
            thread_pool=self.thread_pool,
            recorder=self.recorder,
            video_exporter=self.video_exporter,
            clipboard_service=self.clipboard_service,
            presenter=presenter,
            video_editor_plugin=self.video_editor_plugin,
            main_controller=main_controller,
            event_bus=self.event_bus,
        )
        if presenter and self.controller:
            self.controller.presenter = presenter

        warm_up = getattr(self.video_exporter, "warm_up_gpu_widgets", None)
        if callable(warm_up):
            # Off the startup critical path, well before the video editor
            # dialog is likely to be opened, so the GPU offscreen widgets'
            # cold-start cost (window/QRhi surface creation) isn't paid
            # inline with the user's first thumbnail/preview request. Not
            # every tab can actually provide a canvas widget class (see
            # tab_canvas_services.get_canvas_widget_class), so this fixed
            # delay only succeeds if a tab that can already happens to be
            # the active session by the time it fires — the
            # WorkspaceSessionActivatedEvent subscription below catches the
            # case where the active session changes into (or starts as) a
            # canvas-providing tab at some other point.
            QTimer.singleShot(_GPU_WARM_UP_DELAY_MS, warm_up)

        if self.event_bus:
            self.event_bus.subscribe(
                WorkspaceSessionActivatedEvent, self._on_session_activated
            )

        if self.event_bus and self.controller:

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
            self.event_bus.subscribe(
                ExportPasteImageFromClipboardEvent,
                self.controller.on_paste_image_from_clipboard,
            )

    def _on_session_activated(self, event: WorkspaceSessionActivatedEvent) -> None:
        # Deliberately not filtered by session_type — this file is platform
        # code and must stay tab-agnostic (see
        # tests/contracts/test_platform_isolation.py). warm_up() already
        # best-effort no-ops when the newly active tab doesn't provide a
        # canvas widget class, and _ensure_widget() (called under the hood)
        # is idempotent past its first success, so firing this on every
        # session activation is harmless and catches whichever one actually
        # can provide it, whenever that happens.
        warm_up = getattr(self.video_exporter, "warm_up_gpu_widgets", None)
        if callable(warm_up):
            warm_up()

    def _emit(self, event: str, payload: Any) -> None:
        if self.event_bus:
            self.event_bus.emit(event, payload)

    def get_ui_components(self) -> dict[str, Any]:
        return {}

    def get_controller(self) -> ExportController | None:
        return self.controller

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        if self.controller and hasattr(self.controller, command):
            return getattr(self.controller, command)(*args, **kwargs)
        raise AttributeError(f"Export plugin has no command '{command}'")

    def bind_window_shell(self, window_shell: Any) -> None:
        if self.controller:
            if hasattr(window_shell, "get_feature"):
                self.controller.presenter = window_shell.get_feature("export")
            else:
                self.controller.presenter = window_shell

    def get_service(self) -> Any:
        return self.recorder

    def _collect_video_keyframe_adapters(self) -> tuple[Any, ...]:
        if not self.plugin_coordinator:
            return ()

        adapters: list[Any] = []
        for plugin in self.plugin_coordinator.iter_plugins():
            if plugin is self:
                continue
            if isinstance(plugin, IVideoTrackProvider):
                adapters.extend(plugin.get_video_keyframe_adapters())
        return tuple(adapters)

    def _create_recording_services(
        self,
        *,
        main_controller: Any | None,
        presenter: Any | None,
        extra_adapters: tuple[Any, ...],
    ) -> tuple[Any, Any]:
        plugin = self.video_editor_plugin
        if plugin is None or not hasattr(plugin, "create_recording_services"):
            raise RuntimeError(
                "video_editor plugin must provide recording services for export controls"
            )
        return plugin.create_recording_services(
            store=self.store,
            main_controller=main_controller,
            gpu_export_service=getattr(presenter, "gpu_export_service", None),
            extra_adapters=extra_adapters,
        )

    def _create_clipboard_service(self, main_controller: Any | None) -> Any:
        """Bootstrap-default paste service for early shell wiring.

        Live Ctrl+V resolves through ``ExportController.paste_image_from_clipboard``
        → active-tab ``create_service("clipboard_paste_service")``. This startup
        instance remains as a fallback when no active tab owns paste (e.g.
        session_picker).
        """
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        service = registry.create_startup_service(
            "clipboard_paste_service",
            self.store,
            main_controller,
        )
        if service is None:
            raise RuntimeError(
                "No tab provides clipboard_paste_service; clipboard paste "
                "must be supplied by a tab owner."
            )
        return service

    def provides_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def shutdown(self) -> None:
        super().shutdown()

        if self.video_exporter:
            try:
                self.video_exporter.cleanup()
            except Exception as e:
                import logging

                logging.getLogger("ImproveImgSLI").error(
                    f"Ошибка при завершении VideoExporterService: {e}"
                )
