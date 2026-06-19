from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QTimer

from core.constants import AppConstants
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

def _query_overlay(store, capability_id: str, default=None):
    command = get_canvas_feature_command_by_alias(capability_id)
    if command is None:
        return default
    result = command(store)
    return default if result is None else result

class MagnifierVisibilityController:
    def __init__(self, manager):
        self.manager = manager

    def update_states(self):
        host = self.manager.host
        try:
            model = _query_overlay(host.store, "overlay.active_state")
            show_center = getattr(host.store.viewport.view_state, "diff_mode", "off") != "off"
            left_on = bool(model.get("visible_left", True)) if model is not None else True
            center_on = bool(model.get("visible_center", True)) if model is not None else True
            right_on = bool(model.get("visible_right", True)) if model is not None else True
            host.magnifier_visibility_flyout.set_mode_and_states(
                show_center, left_on, center_on, right_on
            )
        except Exception:
            pass

    def on_toggle_with_hover(self, checked: bool):
        host = self.manager.host
        btn = getattr(host.ui, "btn_magnifier", None)
        if btn is None:
            return
        if not checked:
            try:
                host._magn_hover_timer.stop()
            except Exception:
                pass
            self.hide(reason="main_toggle_disabled")
            return
        if btn.underMouse():
            QTimer.singleShot(0, lambda: self.show(reason="hover"))

    def show(self, reason: str = "hover"):
        host = self.manager.host
        use_magnifier = bool(_query_overlay(host.store, "overlay.enabled", False))
        if not use_magnifier:
            return
        try:
            self.manager.magnifier_instances.hide()
        except Exception:
            pass
        self.update_states()
        btn = getattr(host.ui, "btn_magnifier", None)
        if btn is None:
            return
        host.magnifier_visibility_flyout.show_for_button(
            btn, host.parent_widget, hover_delay_ms=0
        )
        host._magn_popup_open = True
        host._magn_popup_last_open_ts = time.monotonic()
        if reason == "wheel":
            host.magnifier_visibility_flyout.schedule_auto_hide(
                AppConstants.TRANSIENT_WHEEL_AUTO_HIDE_DELAY_MS
            )
        else:
            host.magnifier_visibility_flyout.cancel_auto_hide()

    def hide(self, reason: str = "explicit"):
        host = self.manager.host
        try:
            host._magn_hover_timer.stop()
        except Exception:
            pass
        host.magnifier_visibility_flyout.hide()
        host._magn_popup_open = False

    def event_filter(self, watched, event):
        host = self.manager.host
        btn = getattr(host.ui, "btn_magnifier", None)
        if btn is None:
            return False
        if watched is btn:
            return self._handle_button_event(event)
        if watched is host.magnifier_visibility_flyout:
            return self._handle_flyout_event(event)
        flyout = host.magnifier_visibility_flyout
        if watched in (
            getattr(flyout, "btn_left", None),
            getattr(flyout, "btn_center", None),
            getattr(flyout, "btn_right", None),
        ):
            return self._handle_child_event(event)
        return False

    def _handle_button_event(self, event):
        host = self.manager.host
        et = event.type()
        if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
            host._magn_hover_timer.stop()
            use_magnifier = bool(_query_overlay(host.store, "overlay.enabled", False))
            if use_magnifier:
                host._magn_hover_timer.start(AppConstants.TRANSIENT_HOVER_OPEN_DELAY_MS)
            else:
                host.magnifier_visibility_flyout.hide()
            return False
        if et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            host._magn_hover_timer.stop()
            host.magnifier_visibility_flyout.schedule_auto_hide(
                AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS
            )
            return False
        if et == QEvent.Type.Wheel:
            use_magnifier = bool(_query_overlay(host.store, "overlay.enabled", False))
            if not use_magnifier:
                return True
            self.show(reason="wheel")
            return True
        return False

    def _handle_flyout_event(self, event):
        host = self.manager.host
        et = event.type()
        if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
            host.magnifier_visibility_flyout.cancel_auto_hide()
        elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            host.magnifier_visibility_flyout.schedule_auto_hide(
                AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS
            )
        return False

    def _handle_child_event(self, event):
        flyout = self.manager.host.magnifier_visibility_flyout
        et = event.type()
        if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
            flyout.cancel_auto_hide()
        elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            flyout.schedule_auto_hide(AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS)
        return False
