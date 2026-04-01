from __future__ import annotations

from typing import Any

from core.events import (
    AnalysisRequestMetricsEvent,
    AnalysisSetChannelViewModeEvent,
    AnalysisSetDiffModeEvent,
    AnalysisToggleDiffModeEvent,
)
from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import IControllablePlugin
from core.plugin_system.ui_integration import get_plugin_name
from plugins.analysis.controller import AnalysisController
from plugins.analysis.services import (
    AnalysisRuntime,
    CachedDiffService,
    CoreUpdateDispatcher,
    MetricsService,
    UIUpdateDispatcher,
)
from plugins.analysis.state import AnalysisState

@plugin(name="analysis", version="1.0")
class AnalysisPlugin(Plugin, IControllablePlugin):
    capabilities = ("analysis", "metrics")

    def __init__(self) -> None:
        super().__init__()
        self.controller: AnalysisController | None = None
        self._domain_state: AnalysisState | None = None
        self.metrics_service: MetricsService | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.event_bus = getattr(context, "event_bus", None)
        self.thread_pool = getattr(context, "thread_pool", None)

        if self.store:
            self._domain_state = AnalysisState()
            self.store.viewport.set_analysis_plugin_state(self._domain_state)

        runtime = AnalysisRuntime(
            thread_pool=self.thread_pool,
            ui_updates=UIUpdateDispatcher(event_bus=self.event_bus),
            core_updates=CoreUpdateDispatcher(event_bus=self.event_bus),
        )
        self.metrics_service = MetricsService(self.store, runtime)
        diff_service = CachedDiffService(self.store, runtime)

        ui_registry = getattr(context, "plugin_ui_registry", None)
        if ui_registry and self.metrics_service:
            ui_registry.register_action(
                get_plugin_name(self),
                "trigger_metrics",
                lambda: self.metrics_service.calculate_metrics_async(True, True),
            )

        if self.store and self.thread_pool:
            self.controller = AnalysisController(
                self.store,
                runtime,
                self.metrics_service,
                diff_service,
                self.event_bus,
            )

        if self.event_bus:
            self.event_bus.subscribe(
                AnalysisRequestMetricsEvent, self._on_metrics_requested_event
            )

            if self.controller:
                self.event_bus.subscribe(
                    AnalysisSetChannelViewModeEvent,
                    self.controller.on_set_channel_view_mode,
                )
                self.event_bus.subscribe(
                    AnalysisToggleDiffModeEvent, self.controller.on_toggle_diff_mode
                )
                self.event_bus.subscribe(
                    AnalysisSetDiffModeEvent, self.controller.on_set_diff_mode
                )

    def _on_metrics_requested(self, payload: dict[str, Any] | None = None) -> None:
        calc_psnr = payload.get("psnr", True) if payload else True
        calc_ssim = payload.get("ssim", True) if payload else True
        if self.metrics_service is not None:
            self.metrics_service.calculate_metrics_async(calc_psnr, calc_ssim)

    def _on_metrics_requested_event(self, event: AnalysisRequestMetricsEvent) -> None:
        self._on_metrics_requested(event.payload)

    def get_ui_components(self) -> dict[str, Any]:
        return {
            "trigger_metrics": lambda psnr=True, ssim=True: self.metrics_service.calculate_metrics_async(
                psnr, ssim
            )
            if self.metrics_service is not None
            else None
        }

    def get_controller(self) -> AnalysisController | None:
        return self.controller

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        if not self.controller:
            raise RuntimeError("Analysis controller is not initialized")
        target = getattr(self.controller, command, None)
        if callable(target):
            return target(*args, **kwargs)
        raise AttributeError(f"Analysis controller has no command '{command}'")
