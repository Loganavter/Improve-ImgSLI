from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal
from shared_toolkit.workers import GenericWorker
from resources.translations import tr
from core.events import (
    CoreErrorOccurredEvent,
    ExportToggleRecordingEvent,
    ExportTogglePauseRecordingEvent,
    ExportExportRecordedVideoEvent,
    ExportOpenVideoEditorEvent,
    ExportPasteImageFromClipboardEvent,
    ExportQuickSaveComparisonEvent,
)
import logging

logger = logging.getLogger("ImproveImgSLI")

class ExportController(QObject):

    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        store,
        thread_pool,
        recorder,
        video_exporter,
        clipboard_service,
        presenter=None,
        video_editor_plugin: Any | None = None,
        main_controller=None,
        event_bus=None,
    ):
        super().__init__()
        self.store = store
        self.thread_pool = thread_pool
        self.recorder = recorder
        self.video_exporter = video_exporter
        self.clipboard_service = clipboard_service
        self.presenter = presenter
        self._toggle_recording_in_progress = False
        self.video_editor_plugin = video_editor_plugin
        self.main_controller = main_controller
        self.event_bus = event_bus

    def _get_ui(self):
        if self.presenter and hasattr(self.presenter, 'main_window_app'):
            return getattr(self.presenter.main_window_app, 'ui', None)
        if self.main_controller and hasattr(self.main_controller, 'presenter'):
            return getattr(self.main_controller.presenter, 'ui', None)
        return None

    def toggle_recording(self, checked: bool = None):

        if self._toggle_recording_in_progress:
            return
        self._toggle_recording_in_progress = True

        try:
            ui = self._get_ui()
            if self.recorder.is_recording:
                self.recorder.stop()

                try:
                    snapshots_count = 0
                    if hasattr(self.recorder, "snapshots") and self.recorder.snapshots:
                        snapshots_count = len(self.recorder.snapshots)
                except Exception:
                    pass
                if ui and hasattr(ui, 'btn_record'):

                    ui.btn_record.blockSignals(True)
                    ui.btn_record.setChecked(False)
                    ui.btn_record.blockSignals(False)

                    ui.btn_pause.setChecked(False)
                    ui.btn_pause.setEnabled(False)
            else:
                self.recorder.start()

                if ui and hasattr(ui, 'btn_record'):

                    ui.btn_record.blockSignals(True)
                    ui.btn_record.setChecked(True)
                    ui.btn_record.blockSignals(False)

                    ui.btn_pause.setEnabled(True)
                    ui.btn_pause.setChecked(False)
        finally:
            self._toggle_recording_in_progress = False

    def toggle_pause_recording(self, checked: bool = None):

        ui = self._get_ui()
        if not self.recorder.is_recording:
            if ui and hasattr(ui, 'btn_pause'):
                ui.btn_pause.setChecked(False)
            return

        is_paused = self.recorder.toggle_pause()

        if ui and hasattr(ui, 'btn_pause'):
            ui.btn_pause.setChecked(is_paused)

    def export_recorded_video(self, resolution=(1920, 1080), fps=60):
        if not self.recorder.snapshots:
            return

        if self.event_bus:
            self.event_bus.emit(CoreErrorOccurredEvent(tr("msg.starting_video_export_please_wait", self.store.settings.current_language)))
        else:
            self.error_occurred.emit(tr("msg.starting_video_export_please_wait", self.store.settings.current_language))

        worker = GenericWorker(self.video_exporter.export_recorded_video, resolution, fps)

        worker.signals.result.connect(lambda path: logger.info(f"Export finished: {path}"))
        worker.signals.error.connect(lambda err: logger.error(f"Export failed: {err}"))

        self.thread_pool.start(worker)

    def open_video_editor(self, checked: bool = False):

        if not self.recorder.snapshots:
            if self.event_bus:
                self.event_bus.emit(CoreErrorOccurredEvent("No recording available to edit."))
            else:
                self.error_occurred.emit("No recording available to edit.")
            return

        if self.recorder.is_recording:
            self.toggle_recording()

        if self.video_editor_plugin:
            snapshots_copy = list(self.recorder.snapshots)
            main_window_app = getattr(self.presenter, "main_window_app", None)
            self.video_editor_plugin.open_editor(snapshots_copy, self, main_window_app)
            return

        from plugins.video_editor.dialog import VideoEditorDialog

        snapshots_copy = list(self.recorder.snapshots)

        dialog = VideoEditorDialog(snapshots_copy, self, self.presenter.main_window_app)
        dialog.exec()

    def export_video_from_editor(self, frames, fps, resolution=(1920, 1080), options=None):
        if self.event_bus:
            self.event_bus.emit(CoreErrorOccurredEvent(tr("msg.starting_video_export_please_wait", self.store.settings.current_language)))
        else:
            self.error_occurred.emit(tr("msg.starting_video_export_please_wait", self.store.settings.current_language))

        w, h = resolution
        w = w if w % 2 == 0 else w - 1
        h = h if h % 2 == 0 else h - 1
        safe_resolution = (w, h)

        def export_task(progress_callback):
            return self.video_exporter.export_recorded_video(
                safe_resolution,
                fps,
                snapshots_override=frames,
                export_options=options,
                progress_callback=progress_callback,
            )

        worker = GenericWorker(export_task)

        if hasattr(self, "main_controller") and hasattr(self.main_controller, "video_export_progress"):
            worker.signals.progress.connect(self.main_controller.video_export_progress.emit)
            worker.kwargs["progress_callback"] = worker.signals.progress

        def on_success(path):
            if path:
                logger.info(f"Video export finished: {path}")

                if hasattr(self, "main_controller") and hasattr(self.main_controller, "video_export_finished"):
                    self.main_controller.video_export_finished.emit(True)

                if self.presenter and hasattr(self.presenter.main_window_app, "notify_system"):
                    self.presenter.main_window_app.notify_system(
                        "Video Exported",
                        f"Saved to: {path}",
                        image_path=None,
                    )
            else:
                if hasattr(self, "main_controller") and hasattr(self.main_controller, "video_export_finished"):
                    self.main_controller.video_export_finished.emit(False)

        def on_error(err):
            logger.error(f"Video export failed: {err}")
            if self.event_bus:
                self.event_bus.emit(CoreErrorOccurredEvent(f"Video export failed: {err}"))
            else:
                self.error_occurred.emit(f"Video export failed: {err}")
            if hasattr(self, "main_controller") and hasattr(self.main_controller, "video_export_finished"):
                self.main_controller.video_export_finished.emit(False)

        worker.signals.result.connect(on_success)
        worker.signals.error.connect(on_error)

        self.thread_pool.start(worker)

    def paste_image_from_clipboard(self):
        return self.clipboard_service.paste_image_from_clipboard()

    def quick_save_comparison(self, checked: bool = False):
        logger.info("quick_save_comparison called in controller")
        try:
            presenter = getattr(self, "presenter", None)
            if not presenter:
                logger.error("quick_save_comparison: presenter is None")
                return False
            if not hasattr(presenter, "quick_save"):
                logger.error("quick_save_comparison: presenter has no quick_save method")
                return False
            logger.info("quick_save_comparison: calling presenter.quick_save()")

            presenter.quick_save()
            return True
        except Exception as e:
            logger.error(f"Error during quick save delegation: {e}", exc_info=True)
            return False

    def on_toggle_recording(self, event: ExportToggleRecordingEvent):
        self.toggle_recording()

    def on_toggle_pause_recording(self, event: ExportTogglePauseRecordingEvent):
        self.toggle_pause_recording()

    def on_export_recorded_video(self, event: ExportExportRecordedVideoEvent):
        self.export_recorded_video()

    def on_open_video_editor(self, event: ExportOpenVideoEditorEvent):
        self.open_video_editor()

    def on_paste_image_from_clipboard(self, event: ExportPasteImageFromClipboardEvent):
        self.paste_image_from_clipboard()

    def on_quick_save_comparison(self, event: ExportQuickSaveComparisonEvent):
        self.quick_save_comparison()

