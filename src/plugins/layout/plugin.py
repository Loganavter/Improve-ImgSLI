from typing import Any

from plugins.settings.events import SettingsUIModeChangedEvent
from core.plugin_system import Plugin, plugin


def _widget_in_content_subtree(widget, content) -> bool:
    """True when ``widget`` renders inside the below-strip content area.

    Mirrors ``ui.main_window.ui._widget_in_content_subtree`` (kept local:
    plugins must not import presenter internals). Fail-open (True) for
    non-widget doubles and when the content host is not built yet
    (startup fallback).
    """
    if content is None or not hasattr(content, "parentWidget"):
        return True
    if widget is None or not hasattr(widget, "parentWidget"):
        return True
    node = widget
    for _ in range(100):
        if node is content:
            return True
        try:
            node = node.parentWidget()
        except RuntimeError:
            return False
        if node is None:
            return False
    return False


def _resolve_content_host(parent_window):
    """Below-strip content host if built, else None (startup fallback)."""
    content = getattr(parent_window, "workspace_content_widget", None)
    if content is not None:
        return content
    ui_obj = getattr(parent_window, "ui", None)
    return getattr(ui_obj, "workspace_content_widget", None)


@plugin(name="layout", version="1.0", startup_tier="bootstrap")
class LayoutPlugin(Plugin):
    def __init__(self):
        super().__init__()
        self.manager = None
        self._toast_manager = None
        self.store = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        event_bus = getattr(context, "event_bus", None)

        if event_bus:

            event_bus.subscribe(
                SettingsUIModeChangedEvent, self._on_ui_mode_changed_event
            )

    def _on_ui_mode_changed_event(self, event: SettingsUIModeChangedEvent):
        self.on_ui_mode_changed(event.ui_mode)

    def setup_ui_reference(self, ui, parent_window=None):
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        self.manager = registry.create_startup_service("layout_manager", ui, parent_window)
        if self.manager is not None and self.store:
            current_mode = getattr(self.store.settings, "ui_mode", "beginner")
            self.manager.apply_mode(current_mode)

        if self._toast_manager is None and parent_window is not None:
            from sli_ui_toolkit.widgets import ToastManager

            self._toast_manager = ToastManager(parent_window)
            try:
                anchor = registry.create_service("toast_anchor_widget")
            except Exception:
                anchor = None
            if anchor is not None and _widget_in_content_subtree(
                anchor, _resolve_content_host(parent_window)
            ):
                self._toast_manager.set_anchor(anchor)

    @property
    def toast_manager(self):
        return self._toast_manager

    def on_ui_mode_changed(self, mode_name: str):
        if self.manager:
            self.manager.apply_mode(mode_name)
        try:
            from ui.actions.binder import resync_action_shortcuts

            window = getattr(self.manager, "parent_window", None) if self.manager else None
            if window is None and self.manager is not None:
                window = getattr(self.manager, "window", None)
            resync_action_shortcuts(window)
        except Exception:
            pass
