from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, Qt, QSize

from core.constants import AppConstants
from sli_ui_toolkit.managers import DelayedActionTimer, scaled_px
from tabs.image_compare.ui.transient_magnifier import (
    bind_wiring,
    latch_transient_shutdown,
    release_wiring,
    transient_shutdown_latched,
)
from ui.managers.transient_ui_parts.anchored_popup import AnchoredPopupBubbleController
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def _instances_popup_size(count: int) -> QSize:
    """Design-px badge box for the instance count, resolved at use time.

    The app ``OverlayLayer.show_popup(size=...)`` channel copies ``size``
    verbatim into ``setFixedSize`` (measured at 1.0/1.5: the box does not
    scale), so the CALLER owns the design-px -> scaled_px conversion. The
    resolved box is built first and handed over as a plain ``QSize``: an
    inline ``scaled_px`` inside a ``size=`` kwarg is what the raw-px gate
    flags as the toolkit Button double-scaling trap.
    """
    width = 26 if count < 10 else 32
    return QSize(scaled_px(width), scaled_px(24))


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
        self._wiring = None
        self._shutdown_done = False
        self._wire_button()

    def _is_latched(self) -> bool:
        return getattr(self, "_shutdown_done", False) or transient_shutdown_latched(
            self.manager
        )

    def _button(self):
        return getattr(self.widget, "btn_magnifier_instances", None)

    def _wire_button(self) -> None:
        button = self._button()
        if button is None:
            logger.debug("[magnifier-instances] _wire_button: no btn_magnifier_instances yet on widget=%s", self.widget)
            return
        if self._is_latched():
            # Shutdown already started: install nothing, arm nothing.
            return
        button.countChanged.connect(self._on_count_changed)
        targets = button.popup_targets() if hasattr(button, "popup_targets") else (button,)
        # Same takeover contract as MagnifierVisibilityController: drop the
        # previous owner before installing, so a second construction for the
        # same widget replaces it instead of double-delivering focus/hover
        # events and firing countChanged twice.
        release_wiring(self.widget, "instances")
        for target in targets:
            target.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            target.installEventFilter(self.manager.host)
        self._wiring = bind_wiring(
            self.widget,
            "instances",
            self.manager.host,
            targets,
            [(button.countChanged, self._on_count_changed)],
        )
        logger.debug(
            "[magnifier-instances] _wire_button: installed on button=%s targets=%s host=%s",
            button,
            targets,
            self.manager.host,
        )

    def _on_count_changed(self, _count: int) -> None:
        self.on_count_changed()

    def teardown(self) -> None:
        """Detach from the button: filters, ``countChanged``, hover timer."""
        try:
            self._hover_timer.stop()
        except Exception:
            pass
        wiring, self._wiring = self._wiring, None
        if wiring is not None:
            wiring.teardown()

    def shutdown(self) -> None:
        """The host window is closing: stop reacting, for good.

        Same latch as ``MagnifierVisibilityController.shutdown`` — one
        toolbar group, one shutdown contract. Left live, a late FocusOut here
        restarted the popup's auto-hide and a late ``countChanged`` re-showed
        it after the window was gone.
        """
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True
        latch_transient_shutdown(self.manager)
        self._requested_open = False
        try:
            self._hover_timer.stop()
        except Exception:
            pass
        try:
            self._bubble.hide()
        except Exception:
            pass
        self.teardown()

    def _mark_closed(self) -> None:
        self.manager.host._magn_instances_popup_open = False

    def event_filter(self, watched, event):
        if self._is_latched():
            return False
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
        if self._is_latched():
            return
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
            size=_instances_popup_size(count),
            position="top",
            offset=6,
        )
        if shown:
            self.manager.host._magn_instances_popup_open = True

    def hide(self):
        if self._is_latched():
            return
        self._requested_open = False
        self._hover_timer.stop()
        self._bubble.hide()

    def on_count_changed(self):
        if self._is_latched():
            return
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
