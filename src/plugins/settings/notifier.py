from __future__ import annotations

import logging

from core.events import CoreUpdateRequestedEvent
from plugins.settings.events import SettingsUIModeChangedEvent

logger = logging.getLogger("ImproveImgSLI")


class SettingsUpdateNotifier:
    """Fan-out for settings-driven UI updates.

    Delivery guarantee: ``request_core_update`` delivers via ``event_bus``
    when present, else via ``update_requested_signal``. If NEITHER channel
    exists the request is logged loudly (warning) — a settings change with
    zero delivery and zero log lines would leave stale UI with no trace.
    ``emit_ui_mode_changed`` is bus-only by design (mode changes have no
    signal equivalent); without a bus there are no subscribers, so the
    event is dropped — loudly (warning), never silently.
    """

    def __init__(self, store, event_bus=None, update_requested_signal=None):
        self.store = store
        self.event_bus = event_bus
        self.update_requested_signal = update_requested_signal

    def emit_state_change(self, scope: str | None = None):
        if scope is None:
            self.store.emit_state_change()
            return
        self.store.emit_state_change(scope)

    def invalidate_render_cache(self):
        self.store.invalidate_render_cache()

    def request_core_update(self):
        if self.event_bus:
            self.event_bus.emit(CoreUpdateRequestedEvent())
            return
        if self.update_requested_signal is not None:
            self.update_requested_signal.emit()
            return
        logger.warning(
            "SettingsUpdateNotifier.request_core_update dropped: no event_bus "
            "and no update_requested_signal — core will not refresh"
        )

    def emit_ui_mode_changed(self, mode: str):
        if self.event_bus:
            self.event_bus.emit(SettingsUIModeChangedEvent(mode))
            return
        logger.warning(
            "SettingsUpdateNotifier.emit_ui_mode_changed(%r) dropped: no "
            "event_bus (bus-only event, no signal fallback)",
            mode,
        )