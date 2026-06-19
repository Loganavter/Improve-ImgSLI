from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from plugins.export.events import (
    ExportExportRecordedVideoEvent,
    ExportOpenVideoEditorEvent,
    ExportPasteImageFromClipboardEvent,
    ExportQuickSaveComparisonEvent,
    ExportTogglePauseRecordingEvent,
    ExportToggleRecordingEvent,
)
from plugins.export.services.recording_flow import RecordingFlow
from plugins.export.services.video_export_flow import VideoExportFlow
from resources.translations import tr

logger = logging.getLogger("ImproveImgSLI")

class ExportController(QObject):

    error_occurred = Signal(str)

    def __init__(
        self,
        store,
        thread_pool,
        recorder,
        video_exporter,
        clipboard_service,
        presenter=None,
        video_editor_plugin=None,
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
        self._recording_finalize_in_progress = False
        self._pending_open_editor = False
        self.video_editor_plugin = video_editor_plugin
        self.main_controller = main_controller
        self.event_bus = event_bus
        self.recording_flow = RecordingFlow(self)
        self.video_export_flow = VideoExportFlow(self)

    def _tr(self, key: str) -> str:
        return tr(key, self.store.settings.current_language)

    def toggle_recording(self, checked: bool = None):
        self.recording_flow.toggle_recording(checked)

    def toggle_pause_recording(self, checked: bool = None):
        self.recording_flow.toggle_pause_recording(checked)

    def export_recorded_video(self, resolution=(1920, 1080), fps=60):
        self.video_export_flow.export_recorded_video(resolution, fps)

    def open_video_editor(self, checked: bool = False):
        self.recording_flow.open_video_editor(checked)

    def export_video_from_editor(
        self, frames, fps, resolution=(1920, 1080), options=None
    ):
        self.video_export_flow.export_video_from_editor(
            frames, fps, resolution, options
        )

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
                logger.error(
                    "quick_save_comparison: presenter has no quick_save method"
                )
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
