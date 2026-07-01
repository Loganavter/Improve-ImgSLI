from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QPointF, QRect

class PopupClosingController:
    def __init__(self, manager):
        self.manager = manager
        self._tab_extension = self._resolve_tab_extension()

    def _resolve_tab_extension(self):
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        return registry.create_service("popup_close_extension", self.manager)

    def close_all_flyouts_if_needed(self, global_pos: QPointF):
        host = self.manager.host
        if host._is_modal_active or self._is_inside_interpolation_anchor(global_pos):
            return
        self._close_font_flyout_if_needed(global_pos)
        if self._is_interpolation_grace_period_active():
            return
        unified_active = False
        if self._tab_extension is not None:
            unified_active = bool(self._tab_extension.close_at_pointer(global_pos))
        if not unified_active:
            self._close_interpolation_flyout_if_needed(global_pos)
            return
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

    def on_app_focus_changed(self, old_widget, new_widget):
        host = self.manager.host
        if new_widget is None and host.parent_widget.isActiveWindow():
            return
        if self._tab_extension is not None and self._tab_extension.has_focus_inside(new_widget):
            return
        if self._is_widget_alive_and_visible(host.font_settings_flyout):
            if new_widget is not None:
                parent = new_widget
                while parent is not None:
                    if parent is host.font_settings_flyout:
                        return
                    parent = parent.parent()
            if hasattr(host.font_settings_flyout, "has_active_dialog") and host.font_settings_flyout.has_active_dialog():
                return
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
        anchor = host._font_anchor_widget or getattr(host.ui, "btn_text_settings", None)
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
