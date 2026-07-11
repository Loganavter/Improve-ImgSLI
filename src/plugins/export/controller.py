from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from plugins.export.events import (
    ExportOpenVideoEditorEvent,
    ExportPasteImageFromClipboardEvent,
    ExportTogglePauseRecordingEvent,
    ExportToggleRecordingEvent,
)
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
        self.recording_flow, self.video_export_flow = (
            video_editor_plugin.create_control_flows(self)
        )

    def _tr(self, key: str) -> str:
        return tr(key, self.store.settings.current_language)

    def toggle_recording(self, checked: bool = None):
        self.recording_flow.toggle_recording(checked)

    def toggle_pause_recording(self, checked: bool = None):
        self.recording_flow.toggle_pause_recording(checked)

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

    def on_toggle_recording(self, event: ExportToggleRecordingEvent):
        self.toggle_recording()

    def on_toggle_pause_recording(self, event: ExportTogglePauseRecordingEvent):
        self.toggle_pause_recording()

    def on_open_video_editor(self, event: ExportOpenVideoEditorEvent):
        self.open_video_editor()

    def on_paste_image_from_clipboard(self, event: ExportPasteImageFromClipboardEvent):
        self.paste_image_from_clipboard()
