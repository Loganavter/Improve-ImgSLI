from __future__ import annotations

import logging

from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

logger = logging.getLogger("ImproveImgSLI")

# Aliases in the ``preview.*`` namespace are feature-neutral: any feature
# can implement them. The magnifier owns the only implementation today.

class OverlayPreviewController:
    """Orchestrates the shift-hold preview lifecycle.

    The controller is feature-neutral: it calls ``preview.*`` capability
    aliases and treats the snapshot returned by ``preview.snapshot`` as an
    opaque dict, restoring it later via ``preview.restore``.
    """

    def __init__(self, handler):
        self.handler = handler
        self._quick_preview_active = False
        self._snapshot: dict | None = None

    def log_preview_debug(self, message: str, **extra) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return self._quick_preview_active

    def begin(self) -> None:
        command = get_canvas_feature_command_by_alias("preview.snapshot")
        if command is None:
            return
        result = command(self.handler.store)
        if result is None:
            return
        self._quick_preview_active = True
        self._snapshot = dict(result)
        self.log_preview_debug("begin_shift_preview")

    def restore(self) -> None:
        if not self._quick_preview_active:
            return

        snapshot = self._snapshot or {}
        self._quick_preview_active = False
        self._snapshot = None

        command = get_canvas_feature_command_by_alias("preview.restore")
        if command is None:
            return
        changed = command(self.handler.store, **snapshot)
        if changed:
            self.log_preview_debug("restore_shift_preview")
            self._notify_state_change()

    def switch_side(self, side: str) -> None:
        command = get_canvas_feature_command_by_alias("preview.set_side")
        if command is not None:
            command(self.handler.store, side=side)
        self.log_preview_debug("shift_preview_switched", side=side)
        self._notify_state_change()

    def start_side_preview(self, side: str) -> None:
        self.begin()
        command = get_canvas_feature_command_by_alias("preview.set_side")
        if command is not None:
            command(self.handler.store, side=side)
        self.log_preview_debug("shift_preview_started", side=side)
        self._notify_state_change()

    def _notify_state_change(self) -> None:
        self.handler.store.emit_state_change()
        emit_cmd = get_canvas_feature_command_by_alias("preview.emit_changed")
        if emit_cmd is not None:
            emit_cmd(self.handler.store, event_bus=self.handler.event_bus)
        if self.handler.main_controller:
            self.handler.main_controller.update_requested.emit()
