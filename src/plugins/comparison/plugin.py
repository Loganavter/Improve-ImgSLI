from __future__ import annotations

from typing import Any

from core.events import (
    ComparisonErrorEvent,
    ComparisonUpdateRequestedEvent,
)
from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import ISessionPlugin
from core.session_blueprints import SessionBlueprint, SessionResourceBlueprint
from plugins.analysis.services import (
    AnalysisRuntime,
    CachedDiffService,
    CoreUpdateDispatcher,
    MetricsService,
    UIUpdateDispatcher,
)
from plugins.comparison.session_controller import SessionController
from services.io.image_loader import ImageLoaderService
from services.workflow.playlist import PlaylistManager

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
        self.image_loader: ImageLoaderService | None = None
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
        self.image_loader = ImageLoaderService(self.store, None)

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
            self.image_loader,
            self.playlist_manager,
            self.metrics_service,
            diff_service=diff_service,
            event_bus=self.event_bus,
        )
        self.image_loader.main_controller = self.session_ctrl

    def _emit_error(self, message: str) -> None:
        if self.event_bus:
            self.event_bus.emit(ComparisonErrorEvent(message))

    def _emit_update(self) -> None:
        if self.event_bus:
            self.event_bus.emit(ComparisonUpdateRequestedEvent())

    def bind_window_shell(self, window_shell: Any) -> None:
        self.presenter = window_shell
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
                resource_namespaces=(
                    SessionResourceBlueprint("comparison"),
                    SessionResourceBlueprint("analysis"),
                ),
                metadata_defaults={"plugin": "comparison"},
            ),
        )
