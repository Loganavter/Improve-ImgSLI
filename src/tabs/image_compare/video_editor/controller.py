from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from plugins.export.events import (
    ExportOpenVideoEditorEvent,
    ExportTogglePauseRecordingEvent,
    ExportToggleRecordingEvent,
)
from tabs.image_compare.video_editor.services.export_flow import VideoExportFlow
from tabs.image_compare.video_editor.services.recording_flow import RecordingFlow

logger = logging.getLogger("ImproveImgSLI")


class VideoEditorController(QObject):
    error_occurred = Signal(str)

    def __init__(
        self,
        *,
        store,
        thread_pool,
        recorder,
        video_exporter,
        video_editor_plugin,
        presenter=None,
        main_controller=None,
        event_bus=None,
    ):
        super().__init__()
        self.store = store
        self.thread_pool = thread_pool
        self.recorder = recorder
        self.video_exporter = video_exporter
        self.video_editor_plugin = video_editor_plugin
        self.presenter = presenter
        self.main_controller = main_controller
        self.event_bus = event_bus
        self._toggle_recording_in_progress = False
        self._recording_finalize_in_progress = False
        self._pending_open_editor = False
        self.recording_flow = RecordingFlow(self)
        self.video_export_flow = VideoExportFlow(self)

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

    def on_toggle_recording(self, event: ExportToggleRecordingEvent):
        self.toggle_recording()

    def on_toggle_pause_recording(self, event: ExportTogglePauseRecordingEvent):
        self.toggle_pause_recording()

    def on_open_video_editor(self, event: ExportOpenVideoEditorEvent):
        self.open_video_editor()
