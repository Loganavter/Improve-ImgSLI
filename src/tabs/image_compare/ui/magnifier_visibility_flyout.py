from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import IndexedToggleFlyout
from ui.icon_manager import AppIcon


class MagnifierVisibilityFlyout(IndexedToggleFlyout):
    def __init__(self, parent_widget: QWidget):
        super().__init__(parent_widget, slot_count=3, slot_icon=AppIcon.MAGNIFIER)
        self.btn_left = self.buttons[0]
        self.btn_center = self.buttons[1]
        self.btn_right = self.buttons[2]
        self.btn_laser = None

    def set_mode_and_states(
        self,
        show_center: bool,
        left_on: bool,
        center_on: bool,
        right_on: bool,
        laser_on: bool = True,
    ):

        active_states = [left_on, center_on, right_on]
        display_numbers = [1, 2, 3]
        self.set_slots(active_states, display_numbers=display_numbers)
        self.btn_center.setVisible(show_center)
        if show_center:
            self.btn_right.set_display_number(3)
        else:
            self.btn_right.set_display_number(2)
