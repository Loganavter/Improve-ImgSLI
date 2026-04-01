import logging

from PyQt6.QtCore import QPointF

from ui.managers.transient_ui_parts import (
    FlyoutController,
    FontSettingsController,
    InterpolationFlyoutController,
    MagnifierVisibilityController,
    PopupClosingController,
)
logger = logging.getLogger("ImproveImgSLI")

class TransientUIManager:
    def __init__(self, host):
        self.host = host
        self.flyouts = FlyoutController(self)
        self.interpolation = InterpolationFlyoutController(self)
        self.font_settings = FontSettingsController(self)
        self.magnifier = MagnifierVisibilityController(self)
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

    def update_magnifier_flyout_states(self):
        self.magnifier.update_states()

    def on_magnifier_toggle_with_hover(self, checked: bool):
        self.magnifier.on_toggle_with_hover(checked)

    def show_magnifier_visibility_flyout(self, reason: str = "hover"):
        self.magnifier.show(reason)

    def hide_magnifier_visibility_flyout(self, reason: str = "explicit"):
        self.magnifier.hide(reason)

    def event_filter(self, watched, event):
        return self.magnifier.event_filter(watched, event)

    def close_all_flyouts_if_needed(self, global_pos: QPointF):
        self.closing.close_all_flyouts_if_needed(global_pos)

    def hide_transient_same_window_ui(self):
        self.closing.hide_transient_same_window_ui()

    def on_app_focus_changed(self, old_widget, new_widget):
        self.closing.on_app_focus_changed(old_widget, new_widget)
