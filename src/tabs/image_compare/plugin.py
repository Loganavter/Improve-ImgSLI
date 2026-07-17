from __future__ import annotations

from typing import Any

import tabs.image_compare.bootstrap_reducers  # noqa: F401 — reducer side effects
from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import ISessionPlugin
from core.session_blueprints import (
    SessionBlueprint,
    SessionResourceBlueprint,
    SessionSlotBlueprint,
)
from tabs.image_compare.models import ImageCompareState
from tabs.image_compare.state.document import DocumentModel


class _ComparisonControllerProxy:
    def __init__(self, plugin: "ComparisonPlugin"):
        self.plugin = plugin
        self.window_shell: Any | None = None

    @property
    def session_ctrl(self):
        return self.plugin.session_ctrl if self.plugin else None

    def set_current_image(self, image_number: int, emit_signal: bool = True) -> None:
        if self.plugin.session_ctrl:
            self.plugin.session_ctrl.set_current_image(
                image_number, emit_signal=emit_signal
            )

    def __getattr__(self, name):
        if self.plugin.session_ctrl and hasattr(self.plugin.session_ctrl, name):
            return getattr(self.plugin.session_ctrl, name)
        raise AttributeError(
            f"'_ComparisonControllerProxy' object has no attribute '{name}'"
        )


@plugin(name="comparison", version="1.0", startup_tier="bootstrap")
class ComparisonPlugin(Plugin, ISessionPlugin):
    def __init__(self):
        super().__init__()
        self.event_bus: Any | None = None
        self.thread_pool: Any | None = None
        self.store: Any | None = None
        self.metrics_service: Any | None = None
        self.main_controller_proxy: _ComparisonControllerProxy | None = None
        self.playlist_manager: Any | None = None
        self.session_ctrl: Any | None = None
        self.presenter: Any | None = None

    def initialize(self, context: Any) -> None:
        from plugins.settings.events import SettingsAnalysisMetricsRequestedEvent
        from tabs.image_compare._session_controller import SessionController
        from tabs.image_compare.events import (
            AnalysisRequestMetricsEvent,
            AnalysisSetChannelViewModeEvent,
            AnalysisSetDiffModeEvent,
            AnalysisToggleDiffModeEvent,
            ComparisonErrorEvent,
            ComparisonUpdateRequestedEvent,
        )
        from tabs.image_compare.services.analysis.runtime import (
            AnalysisRuntime,
            CoreUpdateDispatcher,
            UIUpdateDispatcher,
        )
        from tabs.image_compare.services.analysis.cached_diff import CachedDiffService
        from tabs.image_compare.services.analysis.metrics import MetricsService
        from tabs.image_compare.services.playlist import PlaylistManager

        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.thread_pool = getattr(context, "thread_pool", None)
        self.event_bus = getattr(context, "event_bus", None)
        self.main_controller_proxy = _ComparisonControllerProxy(self)

        runtime = AnalysisRuntime(
            thread_pool=self.thread_pool,
            ui_updates=UIUpdateDispatcher(event_bus=self.event_bus),
            core_updates=CoreUpdateDispatcher(event_bus=self.event_bus),
        )
        self.metrics_service = MetricsService(self.store, runtime)
        diff_service = CachedDiffService(self.store, runtime)
        self.playlist_manager = PlaylistManager(self.store, self.main_controller_proxy)
        self.session_ctrl = SessionController(
            self.store,
            self.thread_pool,
            self.playlist_manager,
            self.metrics_service,
            diff_service=diff_service,
            event_bus=self.event_bus,
        )
        if self.event_bus and self.session_ctrl:
            self.event_bus.subscribe(
                AnalysisRequestMetricsEvent,
                self.session_ctrl.on_metrics_requested_event,
            )
            self.event_bus.subscribe(
                SettingsAnalysisMetricsRequestedEvent,
                self.session_ctrl.on_metrics_requested_event,
            )
            self.event_bus.subscribe(
                AnalysisSetChannelViewModeEvent,
                self.session_ctrl.on_set_channel_view_mode,
            )
            self.event_bus.subscribe(
                AnalysisToggleDiffModeEvent,
                self.session_ctrl.on_toggle_diff_mode,
            )
            self.event_bus.subscribe(
                AnalysisSetDiffModeEvent,
                self.session_ctrl.on_set_diff_mode,
            )

    def _emit_error(self, message: str) -> None:
        from tabs.image_compare.events import ComparisonErrorEvent

        if self.event_bus:
            self.event_bus.emit(ComparisonErrorEvent(message))

    def _emit_update(self) -> None:
        from tabs.image_compare.events import ComparisonUpdateRequestedEvent

        if self.event_bus:
            self.event_bus.emit(ComparisonUpdateRequestedEvent())

    def bind_window_shell(self, window_shell: Any) -> None:
        self.presenter = window_shell
        if self.metrics_service is not None:
            self.metrics_service.runtime.toast_manager_getter = lambda: getattr(
                window_shell, "toast_manager", None
            )
        if self.main_controller_proxy:
            self.main_controller_proxy.window_shell = window_shell
        if self.session_ctrl:
            self.session_ctrl.presenter = window_shell

    def get_ui_components(self) -> dict[str, Any]:
        return {}

    def get_session_blueprints(self) -> tuple[SessionBlueprint, ...]:
        return (
            SessionBlueprint(
                session_type="image_compare",
                plugin_name="comparison",
                title="Image Compare",
                state_slots=(
                    SessionSlotBlueprint(
                        name="image_compare.state",
                        factory=ImageCompareState,
                    ),
                    SessionSlotBlueprint(
                        name="document",
                        factory=DocumentModel,
                    ),
                ),
                resource_namespaces=(
                    SessionResourceBlueprint("comparison"),
                    SessionResourceBlueprint("analysis"),
                ),
                metadata_defaults={"plugin": "comparison"},
            ),
        )
