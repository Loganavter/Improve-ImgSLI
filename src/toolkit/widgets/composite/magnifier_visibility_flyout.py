from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from toolkit.widgets.atomic.numbered_toggle_icon_button import NumberedToggleIconButton
from toolkit.widgets.composite.base_flyout import BaseFlyout

class MagnifierVisibilityFlyout(BaseFlyout):
    def __init__(self, parent_widget: QWidget):
        super().__init__(parent_widget)
        self._parent = parent_widget
        self._anchor_button = None

        self.h_layout = QHBoxLayout()
        self.h_layout.setContentsMargins(0, 0, 0, 0)
        self.h_layout.setSpacing(6)

        self.content_layout.addLayout(self.h_layout)

        self.btn_left = NumberedToggleIconButton(1, self.container)
        self.btn_center = NumberedToggleIconButton(2, self.container)
        self.btn_right = NumberedToggleIconButton(3, self.container)

        for b in (self.btn_left, self.btn_center, self.btn_right):
            self.h_layout.addWidget(b)

        self._count = 3
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._on_auto_hide_timeout)

        self.hide()

    def set_mode_and_states(self, show_center: bool, left_on: bool, center_on: bool, right_on: bool):
        self._count = 3 if show_center else 2
        self.btn_center.setVisible(show_center)

        self.btn_left.setChecked(not left_on, emit_signal=False)
        self.btn_right.setChecked(not right_on, emit_signal=False)
        if show_center:
            self.btn_center.setChecked(not center_on, emit_signal=False)

        self.update_display_numbers(left_on, center_on, right_on, show_center)

        self.adjustSize()

    def update_display_numbers(self, left_on: bool, center_on: bool, right_on: bool, show_center: bool):

        self.btn_left.set_display_number(None)
        self.btn_center.set_display_number(None)
        self.btn_right.set_display_number(None)

        next_num = 1

        if left_on:
            self.btn_left.set_display_number(next_num)
            next_num += 1

        if show_center:
            if center_on:
                self.btn_center.set_display_number(next_num)
                next_num += 1
            else:

                self.btn_center.set_display_number(None)

        if right_on:
            self.btn_right.set_display_number(next_num)
            next_num += 1
    def show_for_button(self, anchor_btn: QWidget, parent_widget: QWidget, hover_delay_ms: int = 0):
        def _do_show():
            self._anchor_button = anchor_btn
            self.show_aligned(anchor_btn, "top")

        if hover_delay_ms > 0:
            QTimer.singleShot(hover_delay_ms, _do_show)
        else:
            _do_show()

    def schedule_auto_hide(self, ms: int):
        if ms <= 0:
            self._auto_hide_timer.stop()
            return
        self._auto_hide_timer.start(ms)

    def cancel_auto_hide(self):
        self._auto_hide_timer.stop()

    def _on_auto_hide_timeout(self):
        if not self.isVisible():
            return

        from PyQt6.QtGui import QCursor
        from PyQt6.QtCore import QPoint
        cursor_pos = QCursor.pos()

        try:
            flyout_global_rect = self.geometry()
            if flyout_global_rect.contains(cursor_pos):

                self.schedule_auto_hide(1000)
                return
        except Exception:
            pass

        if self._anchor_button:
            try:
                button_global_pos = self._anchor_button.mapToGlobal(QPoint(0, 0))
                button_rect = self._anchor_button.rect()
                button_global_rect = button_rect.translated(button_global_pos)
                if button_global_rect.contains(cursor_pos):

                    self.schedule_auto_hide(1000)
                    return
            except Exception:
                pass

        self.hide()

    def hide(self):
        self.cancel_auto_hide()
        super().hide()

    def contains_global(self, global_pos) -> bool:

        return self.geometry().contains(self.parent().mapFromGlobal(global_pos).toPoint())

