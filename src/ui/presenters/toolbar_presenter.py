from PyQt6.QtCore import QObject

from core.store import Store
from ui.presenters.toolbar.connections import connect_signals as connect_signals_impl
from ui.presenters.toolbar.orientation import (
    on_interpolation_combo_clicked,
    on_magnifier_orientation_middle_clicked,
    on_magnifier_orientation_right_clicked,
    on_orientation_middle_clicked,
    on_orientation_right_clicked,
    on_ui_divider_thickness_changed,
    on_ui_magnifier_thickness_changed,
    show_magnifier_orientation_popup,
    toggle_magnifier_divider_visibility,
    update_magnifier_orientation_button_state,
)
from ui.presenters.toolbar.state import (
    check_name_lengths,
    on_color_option_clicked,
    show_divider_color_picker,
    show_magnifier_divider_color_picker,
    update_toolbar_states,
)

class ToolbarPresenter(QObject):
    def __init__(
        self,
        store: Store,
        main_controller,
        ui,
        main_window_app,
        ui_manager=None,
        parent=None,
    ):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.ui = ui
        self.main_window_app = main_window_app
        self.ui_manager = ui_manager
        self.event_bus = main_controller.event_bus if main_controller else None

        self._orientation_popup = None
        self._popup_timer = None

    def connect_signals(self):
        return connect_signals_impl(self)

    def _on_ui_divider_thickness_changed(self, thickness):
        return on_ui_divider_thickness_changed(self, thickness)

    def _on_ui_magnifier_thickness_changed(self, thickness):
        return on_ui_magnifier_thickness_changed(self, thickness)

    def _on_interpolation_combo_clicked(self):
        return on_interpolation_combo_clicked(self)

    def _show_divider_color_picker(self):
        return show_divider_color_picker(self)

    def _show_magnifier_divider_color_picker(self):
        return show_magnifier_divider_color_picker(self)

    def _on_orientation_right_clicked(self):
        return on_orientation_right_clicked(self)

    def _show_magnifier_orientation_popup(self):
        return show_magnifier_orientation_popup(self)

    def _on_magnifier_orientation_right_clicked(self):
        return on_magnifier_orientation_right_clicked(self)

    def _on_orientation_middle_clicked(self):
        return on_orientation_middle_clicked(self)

    def _on_magnifier_orientation_middle_clicked(self):
        return on_magnifier_orientation_middle_clicked(self)

    def _toggle_magnifier_divider_visibility(self):
        return toggle_magnifier_divider_visibility(self)

    def update_magnifier_orientation_button_state(self):
        return update_magnifier_orientation_button_state(self)

    def check_name_lengths(self):
        return check_name_lengths(self)

    def update_toolbar_states(self):
        return update_toolbar_states(self)

    def _on_color_option_clicked(self, option: str):
        return on_color_option_clicked(self, option)
