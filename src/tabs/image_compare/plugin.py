from __future__ import annotations

from typing import Any

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import ISessionPlugin
from core.session_blueprints import (
    SessionBlueprint,
    SessionResourceBlueprint,
    SessionSlotBlueprint,
)
from core.state_management.extension_reducers import (
    register_render_config_reducer,
    register_session_data_reducer,
)
from core.state_management.slot_reducers import register_state_slot_reducer
from tabs.image_compare.models import ImageCompareState

# `tabs.image_compare.plugins.video_editor` is a nested subpackage, so
# PluginRegistry._scan_package("tabs") (one level deep) never imports its
# plugin.py on its own — import it here for the @plugin decorator's
# registration side effect. Its i18n root is registered by
# `ImageCompareTab.extra_i18n_roots` (see tab.py), not here, since this
# module must not import the host's translation infrastructure directly.
from tabs.image_compare.plugins.video_editor.plugin import VideoEditorPlugin  # noqa: F401
from tabs.image_compare.state.document import DocumentModel
from tabs.image_compare.state.reducer import DocumentReducer
from tabs.image_compare.state.reducers import (
    ImageRenderConfigReducer,
    SessionDataReducer,
)

register_state_slot_reducer("document", DocumentReducer.reduce)
register_session_data_reducer("image_compare", SessionDataReducer().reduce)
register_render_config_reducer(ImageRenderConfigReducer.reduce)
from tabs.image_compare.services.analysis import (
    AnalysisRuntime,
    CachedDiffService,
    CoreUpdateDispatcher,
    MetricsService,
    UIUpdateDispatcher,
)
from tabs.image_compare.events import (
    AnalysisRequestMetricsEvent,
    AnalysisSetChannelViewModeEvent,
    AnalysisSetDiffModeEvent,
    AnalysisToggleDiffModeEvent,
    ComparisonErrorEvent,
    ComparisonUpdateRequestedEvent,
)
from plugins.settings.events import SettingsAnalysisMetricsRequestedEvent
from tabs.image_compare._session_controller import SessionController
from tabs.image_compare.services.playlist import PlaylistManager


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


@plugin(name="comparison", version="1.0")
class ComparisonPlugin(Plugin, ISessionPlugin):
    def __init__(self):
        super().__init__()
        self.event_bus: Any | None = None
        self.thread_pool: Any | None = None
        self.store: Any | None = None
        self.metrics_service: MetricsService | None = None
        self.main_controller_proxy: _ComparisonControllerProxy | None = None
        self.playlist_manager: PlaylistManager | None = None
        self.session_ctrl: SessionController | None = None
        self.presenter: Any | None = None

    def initialize(self, context: Any) -> None:
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
        if self.event_bus:
            self.event_bus.emit(ComparisonErrorEvent(message))

    def _emit_update(self) -> None:
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
