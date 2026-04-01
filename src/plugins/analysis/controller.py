from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from core.events import (
    AnalysisSetChannelViewModeEvent,
    AnalysisSetDiffModeEvent,
    AnalysisToggleDiffModeEvent,
    ViewportUpdateMagnifierCombinedStateEvent,
)
from core.state_management.actions import (
    SetChannelViewModeAction,
    SetDiffModeAction,
    SetInteractiveModeAction,
)
from plugins.analysis.services.cached_diff import CachedDiffService
from plugins.analysis.services.runtime import AnalysisRuntime

class AnalysisController(QObject):
    update_requested = pyqtSignal()

    def __init__(
        self,
        store,
        runtime: AnalysisRuntime,
        metrics_service,
        diff_service: CachedDiffService,
        event_bus=None,
    ):
        super().__init__()
        self.store = store
        self.runtime = runtime
        self.metrics_service = metrics_service
        self.diff_service = diff_service
        self.event_bus = event_bus

    def toggle_diff_mode(self, checked: bool):
        dispatcher = self.store.get_dispatcher() if hasattr(self.store, "get_dispatcher") else None
        if dispatcher is not None:
            dispatcher.dispatch(SetInteractiveModeAction(checked), scope="viewport")
        else:
            self.store.viewport.interaction_state.is_interactive_mode = checked
        self.store.emit_state_change()
        self.runtime.core_updates.emit()

    def set_diff_mode(self, mode: str):
        if self.store.viewport.view_state.diff_mode == mode:
            return

        dispatcher = self.store.get_dispatcher() if hasattr(self.store, "get_dispatcher") else None
        if dispatcher is not None:
            dispatcher.dispatch(SetDiffModeAction(mode), scope="viewport")
        else:
            self.store.viewport.view_state.diff_mode = mode
        self.diff_service.invalidate()

        if mode == "off":
            self.runtime.core_updates.emit()

        self._trigger_metrics_calculation_if_needed()
        self.store.invalidate_render_cache()
        self.store.emit_state_change()

        if self.event_bus:
            self.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())

    def set_channel_view_mode(self, mode: str):
        if self.store.viewport.view_state.channel_view_mode == mode:
            return

        dispatcher = self.store.get_dispatcher() if hasattr(self.store, "get_dispatcher") else None
        if dispatcher is not None:
            dispatcher.dispatch(SetChannelViewModeAction(mode), scope="viewport")
        else:
            self.store.viewport.view_state.channel_view_mode = mode
        if self.store.viewport.view_state.diff_mode != "off":
            self.diff_service.invalidate()

        self.store.invalidate_render_cache()
        self.store.emit_state_change()
        self.runtime.core_updates.emit()

    def _trigger_full_diff_generation(self):
        self.diff_service.request_generation(optimize_ssim=False)

    def _trigger_metrics_calculation_if_needed(self):
        self.metrics_service.trigger_metrics_calculation_if_needed()

    def on_set_channel_view_mode(self, event: AnalysisSetChannelViewModeEvent):
        self.set_channel_view_mode(event.mode)

    def on_toggle_diff_mode(self, event: AnalysisToggleDiffModeEvent):
        self.toggle_diff_mode(True)

    def on_set_diff_mode(self, event: AnalysisSetDiffModeEvent):
        self.set_diff_mode(event.mode)
