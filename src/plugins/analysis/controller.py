from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from shared_toolkit.workers import GenericWorker
from core.events import (
    CoreUpdateRequestedEvent,
    ViewportUpdateMagnifierCombinedStateEvent,
    AnalysisSetChannelViewModeEvent,
    AnalysisToggleDiffModeEvent,
    AnalysisSetDiffModeEvent,
)

class AnalysisController(QObject):

    update_requested = pyqtSignal()

    def __init__(self, store, thread_pool, metrics_service, event_bus=None):
        super().__init__()
        self.store = store
        self.thread_pool = thread_pool
        self.metrics_service = metrics_service
        self.event_bus = event_bus

    def toggle_diff_mode(self, checked: bool):
        self.store.viewport.is_interactive_mode = checked
        self.store.emit_state_change()
        if self.event_bus:
            self.event_bus.emit(CoreUpdateRequestedEvent())
        else:
            self.update_requested.emit()

    def set_diff_mode(self, mode: str):
        if self.store.viewport.diff_mode != mode:
            self.store.viewport.diff_mode = mode
            self.store.viewport.cached_diff_image = None
            if mode != "off":
                self._trigger_full_diff_generation()
            else:
                if self.event_bus:
                    self.event_bus.emit(CoreUpdateRequestedEvent())
                else:
                    self.update_requested.emit()
            self._trigger_metrics_calculation_if_needed()

            self.store.invalidate_render_cache()
            self.store.emit_state_change()

            if self.event_bus:
                self.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())

    def set_channel_view_mode(self, mode: str):
        if self.store.viewport.channel_view_mode != mode:
            self.store.viewport.channel_view_mode = mode

            self.store.invalidate_render_cache()

            self.store.emit_state_change()
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def _trigger_full_diff_generation(self):
        img1 = self.store.document.full_res_image1 or self.store.document.original_image1
        img2 = self.store.document.full_res_image2 or self.store.document.original_image2
        mode = self.store.viewport.diff_mode

        if not img1 or (not img2 and mode != "edges"):
            return

        worker = GenericWorker(self._generate_diff_map_task, img1, img2, mode)
        worker.signals.result.connect(self._on_diff_map_ready)
        self.thread_pool.start(worker, priority=1)

    def _generate_diff_map_task(self, img1, img2, mode):
        try:
            from plugins.analysis.processing import (
                create_highlight_diff,
                create_grayscale_diff,
                create_ssim_map,
                create_edge_map,
            )

            prepared_img2 = img2
            if img2 and img2.size != img1.size:
                prepared_img2 = img2.resize(img1.size, Image.Resampling.LANCZOS)

            diff_mode_handlers = {
                "edges": lambda: create_edge_map(img1),
                "highlight": lambda: create_highlight_diff(img1, prepared_img2, threshold=10),
                "grayscale": lambda: create_grayscale_diff(img1, prepared_img2),
                "ssim": lambda: create_ssim_map(img1, prepared_img2),
            }

            handler = diff_mode_handlers.get(mode)
            return handler() if handler else None
        except Exception:
            return None

    def _on_diff_map_ready(self, diff_image):
        if diff_image:
            self.store.viewport.cached_diff_image = diff_image
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def _trigger_metrics_calculation_if_needed(self):
        self.metrics_service.trigger_metrics_calculation_if_needed()

    def on_set_channel_view_mode(self, event: AnalysisSetChannelViewModeEvent):
        self.set_channel_view_mode(event.mode)

    def on_toggle_diff_mode(self, event: AnalysisToggleDiffModeEvent):
        self.toggle_diff_mode(True)

    def on_set_diff_mode(self, event: AnalysisSetDiffModeEvent):
        self.set_diff_mode(event.mode)

