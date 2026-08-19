from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, Qt, QSize

from core.constants import AppConstants
from sli_ui_toolkit.managers import DelayedActionTimer
from ui.managers.transient_ui_parts.anchored_popup import AnchoredPopupBubbleController

logger = logging.getLogger("ImproveImgSLI")


class MagnifierInstancesPopupController:
    def __init__(self, manager, widget):
        self.manager = manager
        self.widget = widget
        self._requested_open = False
        self._hover_timer = DelayedActionTimer(self.show, parent=manager.host)
        self._bubble = AnchoredPopupBubbleController(
            host=manager.host,
            popup_key="magnifier_instances_popup",
            auto_hide_delay_ms=AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS,
            on_before_show=lambda: self.manager.panel_visibility.hide(
                reason="magnifier_instances_popup"
            ),
            on_hidden=self._mark_closed,
            should_keep_open=lambda: self._requested_open,
        )
        self._wire_button()

    def _button(self):
        return getattr(self.widget, "btn_magnifier_instances", None)

    def _wire_button(self) -> None:
        button = self._button()
        if button is None:
            logger.debug("[magnifier-instances] _wire_button: no btn_magnifier_instances yet on widget=%s", self.widget)
            return
        button.countChanged.connect(lambda _count: self.on_count_changed())
        targets = button.popup_targets() if hasattr(button, "popup_targets") else (button,)
        for target in targets:
            target.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            target.installEventFilter(self.manager.host)
        logger.debug(
            "[magnifier-instances] _wire_button: installed on button=%s targets=%s host=%s",
            button,
            targets,
            self.manager.host,
        )

    def _mark_closed(self) -> None:
        self.manager.host._magn_instances_popup_open = False

    def event_filter(self, watched, event):
        button = self._button()
        if button is None or watched not in button.popup_targets():
            return False

        et = event.type()
        if et in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            logger.debug(
                "[magnifier-instances] watched=%s event=%s reason=%s",
                watched,
                et,
                getattr(event, "reason", lambda: None)(),
            )
        if et == QEvent.Type.Enter:
            self._requested_open = True
            try:
                self.manager.panel_visibility.hide(reason="magnifier_instances_enter")
            except Exception:
                pass
            if not self.manager.host._magn_instances_popup_open:
                self._hover_timer.stop()
                self._hover_timer.start(AppConstants.TRANSIENT_HOVER_OPEN_DELAY_MS)
            else:
                self._bubble.restart_auto_hide()
            return False
        if et == QEvent.Type.Leave:
            self._requested_open = False
            if self.manager.host._magn_instances_popup_open:
                self._bubble.restart_auto_hide()
            return False
        if et == QEvent.Type.FocusIn:
            # Mirror the Enter/hover-open path for keyboard/Tab focus. The
            # reason is read off the event itself rather than the button's
            # `_keyboard_focus` flag, since this filter runs before
            # Button.focusInEvent updates that flag for this same event.
            reason = getattr(event, "reason", lambda: None)()
            if reason not in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.MenuBarFocusReason,
            ):
                self._requested_open = True
                try:
                    self.manager.panel_visibility.hide(reason="magnifier_instances_focus")
                except Exception:
                    pass
                if not self.manager.host._magn_instances_popup_open:
                    self._hover_timer.stop()
                    self._hover_timer.start(AppConstants.TRANSIENT_HOVER_OPEN_DELAY_MS)
                else:
                    self._bubble.restart_auto_hide()
            return False
        if et == QEvent.Type.FocusOut:
            self._requested_open = False
            if self.manager.host._magn_instances_popup_open:
                self._bubble.restart_auto_hide()
            return False
        return False

    def show(self):
        button = self._button()
        if button is None:
            return
        count = int(button.magnifier_count())
        logger.debug("[magnifier-instances] show() count=%s", count)
        if count <= 1:
            self.hide()
            return
        shown = self._bubble.show(
            anchor_widget=button,
            text=str(count),
            size=QSize(26, 24) if count < 10 else QSize(32, 24),
            position="top",
            offset=6,
        )
        if shown:
            self.manager.host._magn_instances_popup_open = True

    def hide(self):
        self._requested_open = False
        self._hover_timer.stop()
        self._bubble.hide()

    def on_count_changed(self):
        button = self._button()
        if button is None:
            return
        if button.magnifier_count() <= 1:
            self.hide()
            return
        # Previously only re-shown if the mouse-hover popup was already
        # open -- a keyboard-driven count change (arrow-key ring focus +
        # Up/Down/Enter on InstancesCounterButton) never triggers the Enter/
        # Leave hover events this popup otherwise relies on, so it silently
        # never appeared for keyboard users. Show it too when the button
        # currently holds the keyboard focus ring, mirroring the hover path.
        keyboard_driven = (
            bool(getattr(button, "_keyboard_focus", False)) and button.hasFocus()
        )
        if self.manager.host._magn_instances_popup_open or keyboard_driven:
            self.show()
