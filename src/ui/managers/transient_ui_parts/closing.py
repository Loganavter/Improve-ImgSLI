from __future__ import annotations

import time

from PyQt6.QtCore import QPoint, QPointF, QRect

class PopupClosingController:
    def __init__(self, manager):
        self.manager = manager

    def close_all_flyouts_if_needed(self, global_pos: QPointF):
        host = self.manager.host
        if host._is_modal_active or self._is_inside_interpolation_anchor(global_pos):
            return
        self._close_magnifier_visibility_if_needed(global_pos)
        self._close_font_flyout_if_needed(global_pos)
        if self._is_interpolation_grace_period_active():
            return
        self._close_button_menu_if_needed(
            global_pos, "_diff_mode_popup_open", "_diff_mode_last_open_ts", getattr(host.ui, "btn_diff_mode", None)
        )
        self._close_button_menu_if_needed(
            global_pos, "_channel_mode_popup_open", "_channel_mode_last_open_ts", getattr(host.ui, "btn_channel_mode", None)
        )
        if host.unified_flyout is None or not host.unified_flyout.isVisible():
            self._close_interpolation_flyout_if_needed(global_pos)
            return
        self._close_unified_flyout_if_needed(global_pos)
        if host._interp_popup_open and host._interp_flyout:
            if (time.monotonic() - host._interp_last_open_ts) >= 0.12:
                combo = getattr(host.ui, "combo_interpolation", None)
                if combo is not None:
                    combo_local_pos = host.parent_widget.mapFromGlobal(global_pos.toPoint())
                    combo_rect = combo.rect()
                    combo_rect.moveTo(combo.mapTo(host.parent_widget, combo_rect.topLeft()))
                    if combo_rect.contains(combo_local_pos):
                        return
                flyout_contains = (
                    host._interp_flyout.contains_global(global_pos.toPoint())
                    if hasattr(host._interp_flyout, "contains_global")
                    else QRect(host._interp_flyout.mapToGlobal(QPoint(0, 0)), host._interp_flyout.size()).contains(global_pos.toPoint())
                )
                if not flyout_contains:
                    self.manager.interpolation.close()

    def hide_transient_same_window_ui(self):
        host = self.manager.host
        try:
            if host.unified_flyout is not None and host.unified_flyout.isVisible():
                host.unified_flyout.start_closing_animation()
                host.ui.combo_image1.setFlyoutOpen(False)
                host.ui.combo_image2.setFlyoutOpen(False)
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
            if host._magn_popup_open and host.magnifier_visibility_flyout is not None:
                self.manager.magnifier.hide(reason="hide_transient_same_window_ui")
        except Exception:
            pass
        try:
            overlay_layer = getattr(host.parent_widget, "overlay_layer", None)
            if overlay_layer is not None:
                overlay_layer.hide_all_popups()
        except Exception:
            pass
        try:
            from shared_toolkit.ui.widgets.atomic.tooltips import PathTooltip
            PathTooltip.get_instance().hide_tooltip()
        except Exception:
            pass
        try:
            from events.drag_drop_handler import DragAndDropService
            service = DragAndDropService.get_instance()
            if service.is_dragging():
                service.cancel_drag()
        except Exception:
            pass

    def on_app_focus_changed(self, old_widget, new_widget):
        host = self.manager.host
        if new_widget is None and host.parent_widget.isActiveWindow():
            return
        if (
            self._is_widget_alive_and_visible(host.unified_flyout)
            and getattr(host.unified_flyout, "_is_refreshing", False)
        ):
            return
        if self._is_widget_alive_and_visible(host.unified_flyout) and new_widget is not None:
            parent = new_widget.parent()
            while parent is not None:
                if parent == host.unified_flyout:
                    return
                parent = parent.parent()
        if self._is_widget_alive_and_visible(host.magnifier_visibility_flyout) and new_widget is not None:
            parent = new_widget
            while parent is not None:
                if parent == host.magnifier_visibility_flyout:
                    return
                parent = parent.parent()
        self.hide_transient_same_window_ui()

    def _is_widget_alive_and_visible(self, widget) -> bool:
        if widget is None:
            return False
        try:
            return bool(widget.isVisible())
        except RuntimeError:
            return False

    def _map_global_to_parent(self, global_pos: QPointF):
        return self.manager.host.parent_widget.mapFromGlobal(global_pos.toPoint())

    def _widget_rect_in_parent(self, widget) -> QRect:
        rect = widget.rect()
        rect.moveTo(widget.mapTo(self.manager.host.parent_widget, rect.topLeft()))
        return rect

    def _is_inside_interpolation_anchor(self, global_pos: QPointF) -> bool:
        combo = getattr(self.manager.host.ui, "combo_interpolation", None)
        return combo is not None and self._widget_rect_in_parent(combo).contains(
            self._map_global_to_parent(global_pos)
        )

    def _close_magnifier_visibility_if_needed(self, global_pos: QPointF):
        host = self.manager.host
        if host.magnifier_visibility_flyout is None or not host.magnifier_visibility_flyout.isVisible():
            return
        btn = getattr(host.ui, "btn_magnifier", None)
        if btn is None:
            return
        inside_btn = self._widget_rect_in_parent(btn).contains(self._map_global_to_parent(global_pos))
        inside_fly = host.magnifier_visibility_flyout.contains_global(global_pos)
        if not inside_btn and not inside_fly:
            self.manager.magnifier.hide(reason="close_all_outside")

    def _close_font_flyout_if_needed(self, global_pos: QPointF):
        host = self.manager.host
        if not (
            host._font_popup_open
            and (time.monotonic() - host._font_popup_last_open_ts) > 0.12
            and host.font_settings_flyout is not None
        ):
            return
        flyout_global_rect = QRect(
            host.font_settings_flyout.mapToGlobal(QPoint(0, 0)),
            host.font_settings_flyout.size(),
        )
        anchor = host._font_anchor_widget or getattr(host.ui, "btn_color_picker", None)
        button_rect = QRect()
        if anchor:
            button_rect = anchor.geometry()
            button_rect.moveTo(anchor.mapToGlobal(QPoint(0, 0)))
        if not flyout_global_rect.contains(global_pos.toPoint()) and not button_rect.contains(global_pos.toPoint()):
            self.manager.font_settings.hide()

    def _is_interpolation_grace_period_active(self) -> bool:
        host = self.manager.host
        return bool(
            hasattr(host, "_interp_last_open_ts")
            and host._interp_last_open_ts > 0
            and (time.monotonic() - host._interp_last_open_ts) < 0.15
        )

    def _close_button_menu_if_needed(self, global_pos: QPointF, open_attr: str, opened_at_attr: str, button):
        host = self.manager.host
        if not getattr(host, open_attr, False):
            return
        if (time.monotonic() - getattr(host, opened_at_attr, 0.0)) <= 0.12:
            return
        if button is None or not button.is_menu_visible():
            setattr(host, open_attr, False)
            return
        local_pos = self._map_global_to_parent(global_pos)
        btn_rect = self._widget_rect_in_parent(button)
        menu_widget = button.menu
        menu_rect = QRect(menu_widget.mapToGlobal(QPoint(0, 0)), menu_widget.size())
        if not btn_rect.contains(local_pos) and not menu_rect.contains(global_pos.toPoint()):
            button.hide_menu()
            setattr(host, open_attr, False)

    def _close_interpolation_flyout_if_needed(self, global_pos: QPointF):
        host = self.manager.host
        if not (host._interp_popup_open and host._interp_flyout is not None):
            return
        if self._is_inside_interpolation_anchor(global_pos):
            return
        flyout_contains = (
            host._interp_flyout.contains_global(global_pos.toPoint())
            if hasattr(host._interp_flyout, "contains_global")
            else QRect(host._interp_flyout.mapToGlobal(QPoint(0, 0)), host._interp_flyout.size()).contains(global_pos.toPoint())
        )
        if not flyout_contains:
            self.manager.interpolation.close()

    def _close_unified_flyout_if_needed(self, global_pos: QPointF):
        host = self.manager.host
        local_pos = host.parent_widget.mapFromGlobal(global_pos.toPoint())
        flyout_rect_local = host.unified_flyout.geometry()
        button_rects = []
        for btn in (host.ui.combo_image1, host.ui.combo_image2):
            rect = btn.rect()
            rect.moveTo(btn.mapTo(host.parent_widget, rect.topLeft()))
            button_rects.append(rect)
        is_click_on_any_button = any(r.contains(local_pos) for r in button_rects)
        is_click_inside_flyout = flyout_rect_local.contains(local_pos)
        is_click_on_flyout_child = self._is_click_on_widget_or_children(
            host.unified_flyout, global_pos.toPoint()
        )
        if hasattr(host.unified_flyout, "panel_left"):
            for panel in [host.unified_flyout.panel_left, host.unified_flyout.panel_right]:
                if hasattr(panel, "list_view") and hasattr(panel.list_view, "custom_v_scrollbar"):
                    scrollbar = panel.list_view.custom_v_scrollbar
                    if scrollbar.isVisible():
                        scrollbar_global_rect = QRect(scrollbar.mapToGlobal(QPoint(0, 0)), scrollbar.size())
                        if scrollbar_global_rect.contains(global_pos.toPoint()):
                            return
        if not is_click_on_any_button and not is_click_inside_flyout and not is_click_on_flyout_child:
            host.unified_flyout.start_closing_animation()
            host.ui.combo_image1.setFlyoutOpen(False)
            host.ui.combo_image2.setFlyoutOpen(False)

    def _is_click_on_widget_or_children(self, widget, global_pos_point):
        if not widget or not widget.isVisible():
            return False
        local_pos_for_widget = widget.mapFromGlobal(global_pos_point)
        return widget.rect().contains(local_pos_for_widget)
