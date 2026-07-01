from __future__ import annotations

from PySide6.QtCore import QEvent, QSize

from core.constants import AppConstants
from sli_ui_toolkit.managers import DelayedActionTimer
from ui.managers.transient_ui_parts.anchored_popup import AnchoredPopupBubbleController


class MagnifierInstancesPopupController:
    def __init__(self, manager):
        self.manager = manager
        self._requested_open = False
        self._hover_timer = DelayedActionTimer(self.show, parent=manager.host)
        self._bubble = AnchoredPopupBubbleController(
            host=manager.host,
            popup_key="magnifier_instances_popup",
            auto_hide_delay_ms=AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS,
            on_before_show=lambda: self.manager.magnifier.hide(
                reason="magnifier_instances_popup"
            ),
            on_hidden=self._mark_closed,
            should_keep_open=lambda: self._requested_open,
        )

    def _button(self):
        return getattr(self.manager.host.ui, "btn_magnifier_instances", None)

    def _mark_closed(self) -> None:
        self.manager.host._magn_instances_popup_open = False

    def event_filter(self, watched, event):
        button = self._button()
        if button is None or watched not in button.popup_targets():
            return False

        et = event.type()
        if et == QEvent.Type.Enter:
            self._requested_open = True
            try:
                self.manager.magnifier.hide(reason="magnifier_instances_enter")
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
        return False

    def show(self):
        button = self._button()
        if button is None:
            return
        count = int(button.magnifier_count())
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
        if self.manager.host._magn_instances_popup_open:
            self.show()
