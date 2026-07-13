from __future__ import annotations

class PopupClosingController:
    def __init__(self, manager):
        self.manager = manager
        self._tab_extension = self._resolve_tab_extension()

    def _resolve_tab_extension(self):
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        return registry.create_startup_service("popup_close_extension", self.manager)

    def close_all_flyouts_if_needed(self, global_pos):
        host = self.manager.host
        if host._is_modal_active:
            return
        if self._tab_extension is not None:
            self._tab_extension.close_at_pointer(global_pos)

    def hide_transient_same_window_ui(self):
        host = self.manager.host
        if self._tab_extension is not None:
            try:
                self._tab_extension.hide_same_window()
            except Exception:
                pass
        try:
            if host._interp_popup_open and host._interp_flyout is not None:
                self.manager.interpolation.close()
        except Exception:
            pass
        try:
            if host._font_popup_open and host.font_settings_flyout is not None:
                self.manager.font_settings.hide()
        except Exception:
            pass
        try:
            overlay_layer = getattr(host.parent_widget, "overlay_layer", None)
            if overlay_layer is not None:
                overlay_layer.hide_all_popups()
        except Exception:
            pass
        try:
            from events.drag_drop_handler import DragAndDropService
            service = DragAndDropService.get_instance()
            if service.is_dragging():
                service.cancel_drag()
        except Exception:
            pass

    def _focus_aware_owners(self):
        return (self._tab_extension, self.manager.interpolation, self.manager.font_settings)

    def on_app_focus_changed(self, old_widget, new_widget):
        host = self.manager.host
        if new_widget is None and host.parent_widget.isActiveWindow():
            return
        for owner in self._focus_aware_owners():
            if owner is not None and owner.has_focus_inside(new_widget):
                return
        self.hide_transient_same_window_ui()
