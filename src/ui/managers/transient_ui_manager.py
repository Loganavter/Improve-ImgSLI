import logging

from PySide6.QtCore import QPointF

from ui.managers.transient_ui_parts import PopupClosingController
logger = logging.getLogger("ImproveImgSLI")

class TransientUIManager:
    def __init__(self, host):
        self.host = host
        self.flyouts = self._create_tab_service("unified_flyout_controller")
        self.interpolation = self._create_tab_service("interpolation_flyout_controller")
        self.font_settings = self._create_tab_service("font_settings_flyout_controller")
        self.magnifier = self._create_tab_service("magnifier_visibility_controller")
        self.magnifier_instances = self._create_tab_service(
            "magnifier_instances_popup_controller"
        )
        self.closing = PopupClosingController(self)

    @property
    def unified_flyout(self):
        return self.host.unified_flyout

    @property
    def font_settings_flyout(self):
        return self.host.font_settings_flyout

    @font_settings_flyout.setter
    def font_settings_flyout(self, value):
        self.host.font_settings_flyout = value

    def mark_font_popup_closed(self):
        self.host._font_popup_open = False

    def _create_tab_service(self, service_id: str):
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        service = registry.create_startup_service(service_id, self)
        if service is None:
            raise RuntimeError(f"Tab transient UI service is unavailable: {service_id}")
        return service

    def show_flyout(self, image_number: int):
        self.flyouts.show_flyout(image_number)

    def sync_flyout_combo_status(self):
        self.flyouts.sync_flyout_combo_status()

    def toggle_interpolation_flyout(self):
        self.interpolation.toggle()

    def show_interpolation_flyout(self):
        self.interpolation.show()

    def apply_interpolation_choice(self, idx: int):
        self.interpolation.apply_choice(idx)

    def close_interpolation_flyout(self):
        self.interpolation.close()

    def on_interpolation_flyout_closed_event(self):
        self.interpolation.on_closed()

    def toggle_font_settings_flyout(self, anchor_widget=None):
        self.font_settings.toggle(anchor_widget=anchor_widget)

    def show_font_settings_flyout(self, anchor_widget=None):
        self.font_settings.show(anchor_widget=anchor_widget)

    def hide_font_settings_flyout(self):
        self.font_settings.hide()

    def repopulate_flyouts(self):
        self.flyouts.repopulate_flyouts()

    def on_font_changed(self):
        self.font_settings.on_font_changed()

    def on_flyout_closed(self, image_number: int):
        self.flyouts.on_flyout_closed(image_number)

    def on_unified_flyout_closed(self):
        self.flyouts.on_unified_flyout_closed()

    def event_filter(self, watched, event):
        if self.magnifier.event_filter(watched, event):
            return True
        return self.magnifier_instances.event_filter(watched, event)

    def close_all_flyouts_if_needed(self, global_pos: QPointF):
        self.closing.close_all_flyouts_if_needed(global_pos)

    def hide_transient_same_window_ui(self, *, reason: str = "transient_ui_manager"):
        self.closing.hide_transient_same_window_ui(reason=reason)

    def on_app_focus_changed(self, old_widget, new_widget):
        self.closing.on_app_focus_changed(old_widget, new_widget)
