from __future__ import annotations

import logging

from core.events import ViewportUpdateMagnifierCombinedStateEvent

logger = logging.getLogger("ImproveImgSLI")

class MagnifierPreviewController:
    def __init__(self, handler):
        self.handler = handler
        self._magnifier_quick_preview_active = False
        self._magnifier_quick_preview_prev_visibility = (True, True)

    def log_preview_debug(self, message: str, **extra) -> None:
        details = ", ".join(f"{key}={value}" for key, value in extra.items())
        logger.debug(
            "[PreviewDebug] %s%s",
            message,
            f" | {details}" if details else "",
        )

    @property
    def is_active(self) -> bool:
        return self._magnifier_quick_preview_active

    def begin(self) -> None:
        viewport = self.handler.store.viewport
        self._magnifier_quick_preview_active = True
        self._magnifier_quick_preview_prev_visibility = (
            viewport.view_state.magnifier_visible_left,
            viewport.view_state.magnifier_visible_right,
        )
        self.log_preview_debug(
            "begin_shift_preview",
            prev_left=viewport.view_state.magnifier_visible_left,
            prev_right=viewport.view_state.magnifier_visible_right,
        )

    def restore(self) -> None:
        if not self._magnifier_quick_preview_active:
            return

        viewport = self.handler.store.viewport
        prev_left, prev_right = self._magnifier_quick_preview_prev_visibility
        self._magnifier_quick_preview_active = False
        self._magnifier_quick_preview_prev_visibility = (True, True)

        if (
            viewport.view_state.magnifier_visible_left != prev_left
            or viewport.view_state.magnifier_visible_right != prev_right
        ):
            viewport.view_state.magnifier_visible_left = prev_left
            viewport.view_state.magnifier_visible_right = prev_right
            self.log_preview_debug(
                "restore_shift_preview",
                left=prev_left,
                right=prev_right,
            )
            self.handler.store.emit_state_change()
            if self.handler.event_bus:
                self.handler.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())
            if self.handler.main_controller:
                self.handler.main_controller.update_requested.emit()

    def switch_side(self, side: str) -> None:
        viewport = self.handler.store.viewport
        viewport.view_state.magnifier_visible_left = side == "left"
        viewport.view_state.magnifier_visible_right = side == "right"
        self.log_preview_debug("shift_preview_switched", side=side)
        self.handler.store.emit_state_change()
        if self.handler.event_bus:
            self.handler.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())
        if self.handler.main_controller:
            self.handler.main_controller.update_requested.emit()

    def start_side_preview(self, side: str) -> None:
        self.begin()
        viewport = self.handler.store.viewport
        viewport.view_state.magnifier_visible_left = side == "left"
        viewport.view_state.magnifier_visible_right = side == "right"
        self.log_preview_debug("shift_preview_started", side=side)
        self.handler.store.emit_state_change()
        if self.handler.event_bus:
            self.handler.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())
        if self.handler.main_controller:
            self.handler.main_controller.update_requested.emit()
