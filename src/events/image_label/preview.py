from __future__ import annotations

import logging

from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

logger = logging.getLogger("ImproveImgSLI")

class OverlayPreviewController:
    def __init__(self, handler):
        self.handler = handler
        self._quick_preview_active = False
        self._quick_preview_prev_visibility = (True, True)

    def log_preview_debug(self, message: str, **extra) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return self._quick_preview_active

    def begin(self) -> None:
        command = get_canvas_feature_command_by_alias("overlay.preview_begin")
        if command is None:
            return
        result = command(self.handler.store)
        if result is None:
            return
        self._quick_preview_active = True
        self._quick_preview_prev_visibility = (
            result["prev_left"],
            result["prev_right"],
        )
        self.log_preview_debug(
            "begin_shift_preview",
            prev_left=result["prev_left"],
            prev_right=result["prev_right"],
        )

    def restore(self) -> None:
        if not self._quick_preview_active:
            return

        prev_left, prev_right = self._quick_preview_prev_visibility
        self._quick_preview_active = False
        self._quick_preview_prev_visibility = (True, True)

        command = get_canvas_feature_command_by_alias("overlay.preview_restore")
        if command is None:
            return
        changed = command(self.handler.store, prev_left=prev_left, prev_right=prev_right)
        if changed:
            self.log_preview_debug(
                "restore_shift_preview",
                left=prev_left,
                right=prev_right,
            )
            self._notify_state_change()

    def switch_side(self, side: str) -> None:
        command = get_canvas_feature_command_by_alias("overlay.preview_set_side")
        if command is not None:
            command(self.handler.store, side=side)
        self.log_preview_debug("shift_preview_switched", side=side)
        self._notify_state_change()

    def start_side_preview(self, side: str) -> None:
        self.begin()
        command = get_canvas_feature_command_by_alias("overlay.preview_set_side")
        if command is not None:
            command(self.handler.store, side=side)
        self.log_preview_debug("shift_preview_started", side=side)
        self._notify_state_change()

    def _notify_state_change(self) -> None:
        self.handler.store.emit_state_change()
        emit_cmd = get_canvas_feature_command_by_alias("overlay.emit_changed")
        if emit_cmd is not None:
            emit_cmd(self.handler.store, event_bus=self.handler.event_bus)
        if self.handler.main_controller:
            self.handler.main_controller.update_requested.emit()
