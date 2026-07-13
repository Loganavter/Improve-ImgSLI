from __future__ import annotations

from domain.qt_adapters import color_to_qcolor

class FontSettingsController:
    def __init__(self, manager, widget):
        self.manager = manager
        self.widget = widget

    def toggle(self, anchor_widget=None):
        host = self.manager.host
        if host._font_popup_open:
            self.hide()
        else:
            self.show(anchor_widget=anchor_widget)

    def show(self, anchor_widget=None):
        host = self.manager.host
        if not host.font_settings_flyout:
            return
        if anchor_widget is None:
            anchor_widget = getattr(self.widget, "btn_text_settings", None)
        host._font_anchor_widget = anchor_widget
        host.font_settings_flyout.set_values(
            host.store.viewport.render_config.font_size_percent,
            host.store.viewport.render_config.font_weight,
            color_to_qcolor(host.store.viewport.render_config.file_name_color),
            color_to_qcolor(host.store.viewport.render_config.file_name_bg_color),
            host.store.viewport.render_config.draw_text_background,
            host.store.viewport.render_config.text_placement_mode,
            getattr(host.store.viewport.render_config, "text_alpha_percent", 100),
            host.store.settings.current_language,
        )
        if anchor_widget is not None:
            host.font_settings_flyout.show_top_left_of(anchor_widget)
            if hasattr(anchor_widget, "setFlyoutOpen"):
                anchor_widget.setFlyoutOpen(True)
        host._font_popup_open = True

    def hide(self):
        host = self.manager.host
        if host.font_settings_flyout is not None:
            host.font_settings_flyout.hide()
        if host._font_anchor_widget is not None and hasattr(
            host._font_anchor_widget, "setFlyoutOpen"
        ):
            host._font_anchor_widget.setFlyoutOpen(False)
        host._font_popup_open = False
        host._font_anchor_widget = None

    def on_font_changed(self):
        host = self.manager.host
        host.repopulate_visible_flyouts()
        self.widget.reapply_button_styles()
        if host.parent_widget is not None:
            host.parent_widget.update()

    def has_focus_inside(self, new_widget) -> bool:
        if new_widget is None:
            return False
        host = self.manager.host
        flyout = host.font_settings_flyout
        if self._is_alive_and_visible(flyout):
            parent = new_widget
            while parent is not None:
                if parent is flyout:
                    return True
                parent = parent.parent()
            if hasattr(flyout, "has_active_dialog") and flyout.has_active_dialog():
                return True
        anchor = host._font_anchor_widget or getattr(self.widget, "btn_text_settings", None)
        if anchor is not None:
            parent = new_widget
            while parent is not None:
                if parent is anchor:
                    return True
                parent = parent.parent()
        return False

    def _is_alive_and_visible(self, widget) -> bool:
        if widget is None:
            return False
        try:
            return bool(widget.isVisible())
        except RuntimeError:
            return False
