from __future__ import annotations

import logging
from typing import Any

from plugins.video_editor.dialog import VideoEditorDialog
from core.plugin_system import Plugin, plugin

logger = logging.getLogger("ImproveImgSLI")

@plugin(name="video_editor", version="1.0")
class VideoEditorPlugin(Plugin):
    def __init__(self):
        super().__init__()

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.event_bus = getattr(context, "event_bus", None)
        self.thread_pool = getattr(context, "thread_pool", None)
        self.store = getattr(context, "store", None)

    def open_editor(self, snapshots: list[Any], export_controller: Any, main_window_app: Any) -> None:
        if not snapshots or not export_controller:
            logger.warning("VideoEditorPlugin.open_editor: snapshots or export_controller is None")
            return

        try:
            logger.debug(f"VideoEditorPlugin.open_editor: Creating dialog with main_window_app={main_window_app}")
            dialog = VideoEditorDialog(snapshots, export_controller, main_window_app)
            logger.debug("VideoEditorPlugin.open_editor: Dialog created, calling exec()")
            dialog.exec()
            logger.debug("VideoEditorPlugin.open_editor: Dialog exec() returned")
        except Exception as e:
            logger.exception(f"VideoEditorPlugin.open_editor: Error creating/showing dialog: {e}")
            raise

    def get_ui_components(self) -> dict[str, Any]:
        return {}

