from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog

from domain.qt_adapters import color_to_qcolor, qcolor_to_color

class SettingsColorActions:
    def __init__(self, store, presenter, main_window_getter):
        self.store = store
        self.presenter = presenter
        self.main_window_getter = main_window_getter

    def show_magnifier_divider_color_picker(self, on_selected):
        dialog = QColorDialog(
            color_to_qcolor(self.store.viewport.render_config.magnifier_divider_color),
            self.main_window_getter(),
        )
        if dialog.exec():
            on_selected(qcolor_to_color(dialog.selectedColor()))

    def apply_smart_magnifier_colors(
        self,
        *,
        set_divider_color,
        set_laser_color,
        set_capture_ring_color,
    ):
        dialog = QColorDialog(
            color_to_qcolor(self.store.viewport.render_config.magnifier_divider_color),
            self.main_window_getter(),
        )
        if not dialog.exec():
            return

        base_color = dialog.selectedColor()
        set_divider_color(qcolor_to_color(base_color))

        laser_color = QColor(base_color)
        laser_color.setAlpha(120)
        set_laser_color(qcolor_to_color(laser_color))

        capture_ring_color = QColor(base_color)
        capture_ring_color.setAlpha(230)
        set_capture_ring_color(qcolor_to_color(capture_ring_color))
