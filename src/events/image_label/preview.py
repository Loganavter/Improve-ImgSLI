from __future__ import annotations

import logging

from core.events import ViewportUpdateMagnifierCombinedStateEvent
from ui.canvas_features.magnifier import MagnifierStoreService

logger = logging.getLogger("ImproveImgSLI")

class MagnifierPreviewController:
    def __init__(self, handler):
        self.handler = handler
        self._scene_state = MagnifierStoreService(handler.store)
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
        model = self._scene_state.ensure_active_magnifier()
        if model is None:
            return
        self._magnifier_quick_preview_active = True
        self._magnifier_quick_preview_prev_visibility = (
            model.visible_left,
            model.visible_right,
        )
        self.log_preview_debug(
            "begin_shift_preview",
            prev_left=model.visible_left,
            prev_right=model.visible_right,
        )

    def restore(self) -> None:
        if not self._magnifier_quick_preview_active:
            return

        prev_left, prev_right = self._magnifier_quick_preview_prev_visibility
        self._magnifier_quick_preview_active = False
        self._magnifier_quick_preview_prev_visibility = (True, True)

        model = self._scene_state.ensure_active_magnifier(create_if_missing=False)
        if model is None:
            return
        if model is not None and (
            model.visible_left != prev_left or model.visible_right != prev_right
        ):
            self._scene_state.set_active_magnifier_visibility_parts(
                left=prev_left,
                right=prev_right,
            )
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
        self._scene_state.set_active_magnifier_visibility_parts(
            left=(side == "left"),
            right=(side == "right"),
        )
        self.log_preview_debug("shift_preview_switched", side=side)
        self.handler.store.emit_state_change()
        if self.handler.event_bus:
            self.handler.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())
        if self.handler.main_controller:
            self.handler.main_controller.update_requested.emit()

    def start_side_preview(self, side: str) -> None:
        self.begin()
        self._scene_state.set_active_magnifier_visibility_parts(
            left=(side == "left"),
            right=(side == "right"),
        )
        self.log_preview_debug("shift_preview_started", side=side)
        self.handler.store.emit_state_change()
        if self.handler.event_bus:
            self.handler.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())
        if self.handler.main_controller:
            self.handler.main_controller.update_requested.emit()
