from __future__ import annotations

import logging

from core.events import CoreUpdateRequestedEvent

logger = logging.getLogger("ImproveImgSLI")

class ViewportRuntime:
    def __init__(self, store, event_bus=None, update_requested_signal=None):
        self.store = store
        self.event_bus = event_bus
        self.update_requested_signal = update_requested_signal
        self.dispatcher = (
            store.get_dispatcher() if hasattr(store, "get_dispatcher") else None
        )

    def dispatch(self, action, *, clear_caches: bool = False) -> bool:
        if self.dispatcher is None:
            logger.warning("Dispatcher not available, using legacy state modification")
            return False

        self.dispatcher.dispatch(action, scope="viewport")
        if clear_caches:
            from core.state_management.actions import InvalidateRenderCacheAction

            self.dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
        return True

    def emit_update(self, *, scope: str | None = None):
        if scope is None:
            self.store.emit_state_change()
        else:
            self.store.emit_state_change(scope)

        if self.event_bus:
            self.event_bus.emit(CoreUpdateRequestedEvent())
        elif self.update_requested_signal is not None:
            self.update_requested_signal.emit()

    def capture_recording_checkpoint(self, *, force_advance_frame: bool = False) -> None:
        recorder = getattr(self.store, "recorder", None)
        if recorder is None:
            return
        if not getattr(recorder, "is_recording", False):
            return
        if getattr(recorder, "is_paused", False):
            return
        recorder.capture_frame(force_advance_frame=force_advance_frame)
