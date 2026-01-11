from __future__ import annotations

from typing import Any

from services.io.image_loader import ImageLoaderService
from services.workflow.playlist import PlaylistManager

from plugins.comparison.session_controller import SessionController
from core.plugin_system import Plugin, plugin
from plugins.analysis.services.metrics import MetricsService
from core.events import (
    ComparisonUIUpdateEvent,
    ComparisonErrorEvent,
    ComparisonUpdateRequestedEvent,
)

class _UIUpdateSignal:
    def __init__(self, event_bus: Any | None):
        self._event_bus = event_bus

    def emit(self, payload: Any) -> None:
        if self._event_bus:

            comps = tuple(payload) if isinstance(payload, (list, tuple)) else ()
            self._event_bus.emit(ComparisonUIUpdateEvent(components=comps))

class _ComparisonControllerProxy:
    def __init__(self, plugin: "ComparisonPlugin"):
        self.plugin = plugin
        self.presenter: Any | None = None
        self.ui_update_requested = _UIUpdateSignal(plugin.event_bus)

    @property
    def session_ctrl(self):
        return self.plugin.session_ctrl if self.plugin else None

    def set_current_image(self, image_number: int, emit_signal: bool = True) -> None:
        if self.plugin.session_ctrl:
            self.plugin.session_ctrl.set_current_image(image_number, emit_signal=emit_signal)

    def __getattr__(self, name):
        if self.plugin.session_ctrl and hasattr(self.plugin.session_ctrl, name):
            return getattr(self.plugin.session_ctrl, name)
        raise AttributeError(f"'_ComparisonControllerProxy' object has no attribute '{name}'")

@plugin(name="comparison", version="1.0")
class ComparisonPlugin(Plugin):
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
        class _MetricsControllerAdapter:
            def __init__(self, thread_pool, event_bus):
                self.thread_pool = thread_pool
                self.ui_update_requested = _UIUpdateSignal(event_bus)

        metrics_controller = _MetricsControllerAdapter(self.thread_pool, self.event_bus)
        self.metrics_service = MetricsService(self.store, metrics_controller)
        self.playlist_manager = PlaylistManager(self.store, self.main_controller_proxy)
        self.session_ctrl = SessionController(
            self.store,
            self.thread_pool,
            self.image_loader,
            self.playlist_manager,
            self.metrics_service,
            event_bus=self.event_bus,
        )
        self.image_loader.main_controller = self.session_ctrl

    def _emit_error(self, message: str) -> None:
        if self.event_bus:
            self.event_bus.emit(ComparisonErrorEvent(message))

    def _emit_update(self) -> None:
        if self.event_bus:
            self.event_bus.emit(ComparisonUpdateRequestedEvent())

    def set_presenter(self, presenter: Any) -> None:
        self.presenter = presenter
        if self.main_controller_proxy:
            self.main_controller_proxy.presenter = presenter
        if self.session_ctrl:
            self.session_ctrl.presenter = presenter

    def get_ui_components(self) -> dict[str, Any]:
        return {}

