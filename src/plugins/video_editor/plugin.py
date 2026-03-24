from __future__ import annotations

import logging
from typing import Any

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import ISessionPlugin
from core.session_blueprints import (
    SessionBlueprint,
    SessionResourceBlueprint,
    SessionSlotBlueprint,
)
from plugins.video_editor.dialog import VideoEditorDialog
from plugins.video_editor.model import VideoSelectionState, VideoTimelineState

logger = logging.getLogger("ImproveImgSLI")

@plugin(name="video_editor", version="1.0")
class VideoEditorPlugin(Plugin, ISessionPlugin):
    def __init__(self):
        super().__init__()
        self._editor_dialog: VideoEditorDialog | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.event_bus = getattr(context, "event_bus", None)
        self.thread_pool = getattr(context, "thread_pool", None)
        self.store = getattr(context, "store", None)

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
            dialog.raise_()
            dialog.activateWindow()
        except RuntimeError:
            self._editor_dialog = None

    def _forget_editor(self, *_args) -> None:
        self._editor_dialog = None

    def get_ui_components(self) -> dict[str, Any]:
        return {}

    def get_session_blueprints(self) -> tuple[SessionBlueprint, ...]:
        return (
            SessionBlueprint(
                session_type="video_compare",
                plugin_name="video_editor",
                title="Video Compare",
                state_slots=(
                    SessionSlotBlueprint(
                        "video.timeline", default=VideoTimelineState().to_dict()
                    ),
                    SessionSlotBlueprint(
                        "video.selection", default=VideoSelectionState().to_dict()
                    ),
                ),
                resource_namespaces=(
                    SessionResourceBlueprint("video"),
                    SessionResourceBlueprint("thumbnails"),
                ),
                metadata_defaults={"plugin": "video_editor"},
            ),
        )
