from __future__ import annotations

import logging
from threading import Event
from typing import Any, Callable

from shared_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import IControllablePlugin, IServicePlugin
from core.plugin_system.ui_integration import get_plugin_name
from core.events import (
    ExportToggleRecordingEvent,
    ExportTogglePauseRecordingEvent,
    ExportExportRecordedVideoEvent,
    ExportOpenVideoEditorEvent,
    ExportPasteImageFromClipboardEvent,
    ExportQuickSaveComparisonEvent,
)
from plugins.export.services.image_export import ExportService
from plugins.video_editor.services.recorder import Recorder
from plugins.video_editor.services.export import VideoExporterService
from plugins.export.controller import ExportController
from services.io.image_loader import ImageLoaderService
from services.system.clipboard import ClipboardService

@plugin(name="export", version="1.0")
class ExportPlugin(Plugin, IControllablePlugin, IServicePlugin):
    capabilities = ("export", "recording")

    def __init__(self):
        super().__init__()
        self.controller: ExportController | None = None
        self.recorder: Recorder | None = None
        self.video_exporter: VideoExporterService | None = None
        self.clipboard_service: ClipboardService | None = None
        self.image_loader: ImageLoaderService | None = None
        self.video_editor_plugin: Any | None = None
        self.export_service: ExportService | None = None
        self.thread_pool: Any | None = None
        self.event_bus: Any | None = None
        self.store: Any | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.thread_pool = getattr(context, "thread_pool", None)
        self.event_bus = getattr(context, "event_bus", None)
        font_path = getattr(context, "font_path_absolute", None)
        self.export_service = ExportService(font_path)
        coordinator = getattr(context, "plugin_coordinator", None)
        self.video_editor_plugin = (
            coordinator.get_plugin("video_editor") if coordinator else None
        )

    def configure_controller(
        self,
        main_controller: Any | None = None,
        presenter: Any | None = None,
    ) -> None:
        if self.controller:
            return
        self.recorder = Recorder(self.store)
        self.video_exporter = VideoExporterService(self.recorder, self.store, main_controller)
        self.image_loader = ImageLoaderService(self.store, main_controller)
        self.clipboard_service = ClipboardService(self.store, main_controller, self.image_loader)
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

        if self.event_bus and self.controller:

            self.event_bus.subscribe(ExportToggleRecordingEvent, self.controller.on_toggle_recording)
            self.event_bus.subscribe(ExportTogglePauseRecordingEvent, self.controller.on_toggle_pause_recording)
            self.event_bus.subscribe(ExportExportRecordedVideoEvent, self.controller.on_export_recorded_video)
            self.event_bus.subscribe(ExportOpenVideoEditorEvent, self.controller.on_open_video_editor)
            self.event_bus.subscribe(ExportPasteImageFromClipboardEvent, self.controller.on_paste_image_from_clipboard)
            self.event_bus.subscribe(ExportQuickSaveComparisonEvent, self.controller.on_quick_save_comparison)

    def quick_save_comparison(self, checked: bool = False) -> bool:
        logger.info("quick_save_comparison called in plugin")
        if self.controller:
            result = self.controller.quick_save_comparison()
            logger.info(f"quick_save_comparison result: {result}")
            return result
        logger.warning("quick_save_comparison: controller is None")
        return False

    def export_image(self, export_options: dict[str, Any], cancel_event: Event | None = None) -> None:
        if not self.export_service or not self.store:
            return

        worker = GenericWorker(self._export_task, export_options, cancel_event, self._progress_callback)
        worker.signals.result.connect(self._on_export_finished)
        worker.signals.error.connect(self._on_export_error)

        if self.thread_pool:
            self.thread_pool.start(worker)
        else:
            worker.run()

    def _export_task(
        self,
        export_options: dict[str, Any],
        cancel_event: Event | None,
        progress_callback: Callable[[int], None],
    ) -> str:
        if not self.store or not self.export_service:
            raise RuntimeError("Missing store or export service.")

        progress_callback(0)
        result = self.export_service.export_image(
            store=self.store,
            original_image1=self.store.document.original_image1,
            original_image2=self.store.document.original_image2,
            export_options=export_options,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
        )
        return result

    def _progress_callback(self, percent: int) -> None:
        self._emit("export.progress", percent)

    def _on_export_finished(self, output_path: Any) -> None:
        self._emit("export.finished", output_path)

    def _on_export_error(self, error_info: Any) -> None:
        self._emit("export.error", error_info)

    def _emit(self, event: str, payload: Any) -> None:
        if self.event_bus:
            self.event_bus.emit(event, payload)

    def get_ui_components(self) -> dict[str, Any]:
        return {
            "export_image": self.export_image,
        }

    def get_controller(self) -> ExportController | None:
        return self.controller

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        if command == "export_image":
            return self.export_image(*args, **kwargs)
        if self.controller and hasattr(self.controller, command):
            return getattr(self.controller, command)(*args, **kwargs)
        raise AttributeError(f"Export plugin has no command '{command}'")

    def set_presenter(self, presenter: Any) -> None:
        if self.controller:

            if hasattr(presenter, 'export_presenter'):
                self.controller.presenter = presenter.export_presenter
            else:

                self.controller.presenter = presenter

    def get_service(self) -> Any:
        return self.recorder

    def provides_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def shutdown(self) -> None:
        super().shutdown()

        if self.video_exporter:
            try:
                self.video_exporter.cleanup()
            except Exception as e:
                import logging
                logging.getLogger("ImproveImgSLI").error(f"Ошибка при завершении VideoExporterService: {e}")

