from __future__ import annotations

import logging
import time

from PySide6.QtCore import QEvent, Qt, QTimer

from core.constants import AppConstants
from sli_ui_toolkit.managers import DelayedActionTimer
from tabs.image_compare.canvas.registry import registry

logger = logging.getLogger("ImproveImgSLI")


def _query_overlay(store, capability_id: str, default=None):
    command = registry().get_feature_command_by_alias(capability_id)
    if command is None:
        return default
    result = command(store)
    return default if result is None else result


class MagnifierVisibilityController:
    def __init__(self, manager, widget):
        self.manager = manager
        self.widget = widget
        self._hover_timer = DelayedActionTimer(
            lambda: self.show(reason="hover"), parent=manager.host
        )
        self._last_flyout_hide_ts = 0.0
        self._wire_button()

    def _wire_button(self) -> None:
        host = self.manager.host
        btn = getattr(self.widget, "btn_magnifier", None)
        if btn is None or self.widget.magnifier_visibility_flyout is None:
            return
        btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        btn.installEventFilter(host)
        self.widget.magnifier_visibility_flyout.installEventFilter(host)
        self.widget.magnifier_visibility_flyout.btn_left.installEventFilter(host)
        self.widget.magnifier_visibility_flyout.btn_center.installEventFilter(host)
        self.widget.magnifier_visibility_flyout.btn_right.installEventFilter(host)
        btn.toggled.connect(self.on_toggle_with_hover)
        # Preview flyout — Down from btn_magnifier enters via extension_below
        # (ToolbarRowsSection.navigate checks extension_below before row jump).
        try:
            from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

            NavigationManager.get_instance().link_below(
                btn, self.widget.magnifier_visibility_flyout
            )
        except Exception:
            pass

    def update_states(self):
        host = self.manager.host
        try:
            model = _query_overlay(host.store, "overlay.active_state")
            show_center = getattr(host.store.viewport.view_state, "diff_mode", "off") != "off"
            left_on = bool(model.get("visible_left", True)) if model is not None else True
            center_on = bool(model.get("visible_center", True)) if model is not None else True
            right_on = bool(model.get("visible_right", True)) if model is not None else True
            self.widget.magnifier_visibility_flyout.set_mode_and_states(
                show_center, left_on, center_on, right_on
            )
        except Exception:
            pass

    def on_toggle_with_hover(self, checked: bool):
        btn = getattr(self.widget, "btn_magnifier", None)
        if btn is None:
            return
        if not checked:
            try:
                self._hover_timer.stop()
            except Exception:
                pass
            self.hide(reason="main_toggle_disabled")
            return
        # Toggling the button with Enter/Space while it holds keyboard focus
        # (no mouse involved) never sets underMouse() -- mirror the hover
        # path for that case too, the same way on_count_changed does for the
        # instances counter, or a keyboard-driven "turn magnifier on" never
        # shows the flyout that mouse users get automatically.
        keyboard_driven = (
            bool(getattr(btn, "_keyboard_focus", False)) and btn.hasFocus()
        )
        if btn.underMouse() or keyboard_driven:
            QTimer.singleShot(0, lambda kd=keyboard_driven: self.show(reason="keyboard" if kd else "hover"))

    def show(self, reason: str = "hover"):
        host = self.manager.host
        use_magnifier = bool(_query_overlay(host.store, "overlay.enabled", False))
        logger.debug("[magnifier-visibility] show() reason=%s use_magnifier=%s", reason, use_magnifier)
        if not use_magnifier:
            return
        # Only explicit Enter/click/wheel may open PanelVisibilityFlyout —
        # hover alone must not (fixes "opens without Enter"). For keyboard
        # opens, keep flyout pinned open (no auto-hide) until explicit close.
        if reason == "hover":
            try:
                from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

                if not NavigationManager.get_instance().last_input_was_keyboard():
                    return
                return
            except Exception:
                return
        try:
            self.manager.panel_instances.hide()
        except Exception:
            pass
        self.update_states()
        btn = getattr(self.widget, "btn_magnifier", None)
        if btn is None:
            return
        # Preview — keep focus on anchor (btn_magnifier) with ring, don't
        # steal into flyout. Down/Enter from anchor (extension_below) will
        # explicitly enter via focus_first_child with ring.
        # register_nav_section=False: preview must not become a nav section
        # — it would otherwise shift positioning (available rect changes with
        # focus proxy) and intercept arrows before Down can enter via
        # extension_below.
        self.widget.magnifier_visibility_flyout.show_for_button(
            btn,
            host.parent_widget,
            hover_delay_ms=0,
            grab_focus=False,
            register_nav_section=False,
        )
        try:
            flyout = self.widget.magnifier_visibility_flyout
            if hasattr(flyout, "_keyboard_navigation_active"):
                flyout._keyboard_navigation_active = False
        except Exception:
            pass
        host._magn_popup_open = True
        host._magn_popup_last_open_ts = time.monotonic()
        if reason == "wheel":
            self.widget.magnifier_visibility_flyout.schedule_auto_hide(
                AppConstants.TRANSIENT_WHEEL_AUTO_HIDE_DELAY_MS
            )
        else:
            self.widget.magnifier_visibility_flyout.cancel_auto_hide()

    def hide(self, reason: str = "explicit"):
        host = self.manager.host
        try:
            self._hover_timer.stop()
        except Exception:
            pass
        self.widget.magnifier_visibility_flyout.hide()
        host._magn_popup_open = False

    def event_filter(self, watched, event):
        host = self.manager.host
        btn = getattr(self.widget, "btn_magnifier", None)
        if btn is None:
            return False
        if watched is btn:
            if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
                logger.debug(
                    "[magnifier-visibility] btn_magnifier event=%s reason=%s",
                    event.type(),
                    getattr(event, "reason", lambda: None)(),
                )
            return self._handle_button_event(event)
        if watched is self.widget.magnifier_visibility_flyout:
            return self._handle_flyout_event(event)
        flyout = self.widget.magnifier_visibility_flyout
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
            # Hover alone no longer opens PanelVisibilityFlyout — only
            # explicit Enter/click (on_toggle_with_hover) does. Hover
            # timer kept for MagnifierSettingsFlyout, but not for this.
            return False
        if et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            return False
        if et == QEvent.Type.FocusIn:
            reason = getattr(event, "reason", lambda: None)()
            is_keyboard = reason not in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.MenuBarFocusReason,
            )
            use_magnifier = bool(_query_overlay(host.store, "overlay.enabled", False))
            if is_keyboard and use_magnifier:
                # Keyboard focus alone shows the panel flyout as a preview
                # (no focus steal) — actual keyboard navigation inside the
                # flyout still requires explicit Enter (see
                # PanelVisibilityFlyout._keyboard_navigation_active).
                self._hover_timer.stop()
                # Use hover delay to avoid flicker on rapid Tab
                self._hover_timer.start(AppConstants.TRANSIENT_HOVER_OPEN_DELAY_MS)
            return False
        if et == QEvent.Type.FocusOut:
            # Don't hide immediately when focus moves to another toolbar
            # control — the flyout is a preview, should stay while focus is
            # anywhere in the magnifier group+flyout unit. Hide is handled
            # via hover leave / explicit Esc, not FocusOut.
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
            self.widget.magnifier_visibility_flyout.cancel_auto_hide()
        elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            self.widget.magnifier_visibility_flyout.schedule_auto_hide(
                AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS
            )
        elif et == QEvent.Type.Hide:
            self._last_flyout_hide_ts = time.monotonic()
        return False

    def _handle_child_event(self, event):
        flyout = self.widget.magnifier_visibility_flyout
        et = event.type()
        if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
            flyout.cancel_auto_hide()
        elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            flyout.schedule_auto_hide(AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS)
        return False
