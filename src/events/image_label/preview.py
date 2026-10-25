from __future__ import annotations

import logging

from shared.debug_flags import env_flag
from ui.canvas_infra.scene.registry import get_canvas_registry
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

def _session_type(store) -> str | None:
    session = store.get_active_workspace_session()
    return session.session_type if session is not None else None

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
        self._session_id = None

    def log_preview_debug(self, message: str, **extra) -> None:
        """Structured preview trace, gated by ``IMGSLI_PREVIEW_DEBUG``.

        Debugging a "the preview did not end" report without these lines is
        guessing: the lifecycle is split between the gesture (begin/switch) and
        two release paths (canvas handler + global handler), and the log is the
        only place that says which one ran and with which snapshot.
        """
        if not env_flag("IMGSLI_PREVIEW_DEBUG"):
            return
        fields = " ".join(f"{key}={value!r}" for key, value in extra.items())
        logger.info("[preview] %s %s", message, fields)

    @property
    def is_active(self) -> bool:
        return self._quick_preview_active

    def _active_session_id(self):
        """Fail-open session identity (None when the store cannot say)."""
        try:
            session = self.handler.store.get_active_workspace_session()
            return getattr(session, "id", None)
        except Exception:
            return None

    def _unwind(self) -> None:
        """Discard the gesture state without applying anything."""
        self._quick_preview_active = False
        self._snapshot = None
        self._session_id = None

    def begin(self) -> None:
        command = get_canvas_registry(_session_type(self.handler.store)).get_feature_command_by_alias(
            "preview.snapshot"
        )
        if command is None:
            return
        result = command(self.handler.store)
        if result is None:
            return
        self._quick_preview_active = True
        self._snapshot = dict(result)
        self._session_id = self._active_session_id()
        self.log_preview_debug("begin_shift_preview", snapshot=self._snapshot)

    def restore(self) -> None:
        if not self._quick_preview_active:
            return
        if self._active_session_id() != self._session_id:
            # Cross-session Shift: the snapshot belongs to another tab —
            # discard without applying (fail-closed) and unwind the gesture.
            logger.warning(
                "OverlayPreviewController.restore: session changed since "
                "begin — discarding snapshot without applying"
            )
            self._unwind()
            return

        snapshot = self._snapshot or {}
        command = get_canvas_registry(_session_type(self.handler.store)).get_feature_command_by_alias(
            "preview.restore"
        )
        if command is None:
            self._unwind()
            return
        try:
            changed = command(self.handler.store, **snapshot)
        except Exception:
            # Fail-closed: never let a half-applied restore propagate — log,
            # discard the snapshot, and unwind the gesture.
            logger.exception("OverlayPreviewController.restore failed")
            self._unwind()
            return
        self._unwind()
        self.log_preview_debug("restore_shift_preview", changed=bool(changed))
        if changed:
            self._notify_state_change()

    def switch_side(self, side: str) -> None:
        command = get_canvas_registry(_session_type(self.handler.store)).get_feature_command_by_alias(
            "preview.set_side"
        )
        if command is not None:
            command(self.handler.store, side=side)
        self.log_preview_debug("shift_preview_switched", side=side)
        self._notify_state_change()

    def start_side_preview(self, side: str) -> None:
        self.begin()
        command = get_canvas_registry(_session_type(self.handler.store)).get_feature_command_by_alias(
            "preview.set_side"
        )
        if command is not None:
            command(self.handler.store, side=side)
        self.log_preview_debug("shift_preview_started", side=side)
        self._notify_state_change()

    def _notify_state_change(self) -> None:
        self.handler.store.emit_state_change()
        emit_cmd = get_canvas_registry(_session_type(self.handler.store)).get_feature_command_by_alias(
            "preview.emit_changed"
        )
        if emit_cmd is not None:
            emit_cmd(self.handler.store, event_bus=self.handler.event_bus)
        if self.handler.main_controller:
            self.handler.main_controller.update_requested.emit()
