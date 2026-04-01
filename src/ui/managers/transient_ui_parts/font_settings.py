from __future__ import annotations

from domain.qt_adapters import color_to_qcolor

class FontSettingsController:
    def __init__(self, manager):
        self.manager = manager

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
            anchor_widget = getattr(host.ui, "btn_color_picker", None)
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
        import time
        host._font_popup_last_open_ts = time.monotonic()

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
        if hasattr(host.ui, "reapply_button_styles"):
            host.ui.reapply_button_styles()
        if host.parent_widget is not None:
            host.parent_widget.update()
