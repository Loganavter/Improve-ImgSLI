from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect

class ImageComparePopupClosing:
    def __init__(self, manager, widget):
        self.manager = manager
        self.widget = widget

    def close_at_pointer(self, global_pos: QPointF) -> bool:
        host = self.manager.host
        if host.unified_flyout is None or not host.unified_flyout.isVisible():
            return False
        self._close_unified_flyout_if_needed(global_pos)
        return True

    def hide_same_window(self) -> None:
        host = self.manager.host
        try:
            if host.unified_flyout is not None and host.unified_flyout.isVisible():
                host.unified_flyout.start_closing_animation()
                self.widget.combo_image1.setFlyoutOpen(False)
                self.widget.combo_image2.setFlyoutOpen(False)
        except Exception:
            pass
        try:
            if host._magn_popup_open and host.magnifier_visibility_flyout is not None:
                self.manager.magnifier.hide(reason="hide_transient_same_window_ui")
        except Exception:
            pass
        try:
            if host._magn_instances_popup_open:
                self.manager.magnifier_instances.hide()
        except Exception:
            pass

    def has_focus_inside(self, new_widget) -> bool:
        host = self.manager.host
        unified = host.unified_flyout
        if self._visible(unified):
            if getattr(unified, "_is_refreshing", False):
                return True
            if new_widget is not None:
                parent = new_widget.parent()
                while parent is not None:
                    if parent is unified:
                        return True
                    parent = parent.parent()
        magnifier_flyout = host.magnifier_visibility_flyout
        if self._visible(magnifier_flyout) and new_widget is not None:
            parent = new_widget
            while parent is not None:
                if parent is magnifier_flyout:
                    return True
                parent = parent.parent()
        return False

    def _visible(self, widget) -> bool:
        if widget is None:
            return False
        try:
            return bool(widget.isVisible())
        except RuntimeError:
            return False

    def _close_unified_flyout_if_needed(self, global_pos: QPointF):
        host = self.manager.host
        local_pos = host.parent_widget.mapFromGlobal(global_pos.toPoint())
        flyout_rect_local = host.unified_flyout.geometry()
        button_rects = []
        for btn in (self.widget.combo_image1, self.widget.combo_image2):
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
                if hasattr(panel, "list_view") and hasattr(
                    panel.list_view, "custom_v_scrollbar"
                ):
                    scrollbar = panel.list_view.custom_v_scrollbar
                    if scrollbar.isVisible():
                        scrollbar_global_rect = QRect(
                            scrollbar.mapToGlobal(QPoint(0, 0)), scrollbar.size()
                        )
                        if scrollbar_global_rect.contains(global_pos.toPoint()):
                            return
        if (
            not is_click_on_any_button
            and not is_click_inside_flyout
            and not is_click_on_flyout_child
        ):
            host.unified_flyout.start_closing_animation()
            self.widget.combo_image1.setFlyoutOpen(False)
            self.widget.combo_image2.setFlyoutOpen(False)

    def _is_click_on_widget_or_children(self, widget, global_pos_point):
        if not widget or not widget.isVisible():
            return False
        local_pos_for_widget = widget.mapFromGlobal(global_pos_point)
        return widget.rect().contains(local_pos_for_widget)
