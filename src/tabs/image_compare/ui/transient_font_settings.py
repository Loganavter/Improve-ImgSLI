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
        # Find Action / cold open: edit row (btn_text_settings) is hidden until
        # filename labels are on — reveal that chrome before anchoring.
        self._ensure_text_settings_chrome()
        anchor_widget = self._resolve_anchor(anchor_widget)
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

    def _ensure_text_settings_chrome(self) -> None:
        """Show the bottom edit toolbar so ``btn_text_settings`` can be anchored."""
        widget = self.widget
        btn = getattr(widget, "btn_text_settings", None)
        if self._is_alive_and_visible(btn):
            return

        host = self.manager.host
        store = getattr(host, "store", None)
        render = getattr(getattr(store, "viewport", None), "render_config", None)
        if store is not None and render is not None and not bool(
            getattr(render, "include_file_names_in_saved", False)
        ):
            from core.state_management.appearance_actions import (
                SetIncludeFileNamesInSavedAction,
            )

            dispatcher = getattr(store, "get_dispatcher", lambda: None)()
            if dispatcher is not None:
                dispatcher.dispatch(
                    SetIncludeFileNamesInSavedAction(True),
                    scope="viewport",
                )

        toggle = getattr(widget, "toggle_edit_layout_visibility", None)
        if callable(toggle):
            toggle(True)

        file_btn = getattr(widget, "btn_file_names", None)
        if file_btn is not None and hasattr(file_btn, "setChecked"):
            try:
                file_btn.setChecked(True, emit_signal=False)
            except TypeError:
                if not bool(file_btn.isChecked()):
                    file_btn.setChecked(True)

        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        except Exception:
            pass

    def _resolve_anchor(self, preferred=None):
        """Prefer a visible text-settings / file-names button for placement."""
        widget = self.widget
        candidates = []
        if preferred is not None:
            candidates.append(preferred)
        for attr in ("btn_text_settings", "btn_file_names"):
            candidate = getattr(widget, attr, None)
            if candidate is not None and candidate not in candidates:
                candidates.append(candidate)
        for candidate in candidates:
            if self._is_alive_and_visible(candidate):
                return candidate
        for candidate in candidates:
            if candidate is not None:
                return candidate
        return None

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
