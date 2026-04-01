import logging

from PyQt6.QtCore import QObject
from core.store import Store
from plugins.settings.presenter_parts import (
    SettingsColorPickerCoordinator,
    SettingsViewStateCoordinator,
)
from resources.translations import tr

logger = logging.getLogger("ImproveImgSLI")

class SettingsPresenter(QObject):

    def __init__(
        self, store: Store, main_controller, ui_manager, main_window_app, parent=None
    ):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.ui_manager = ui_manager
        self.main_window_app = main_window_app
        self.color_pickers = SettingsColorPickerCoordinator(
            store=store,
            main_controller=main_controller,
            main_window_app=main_window_app,
            tr_func=self._tr,
        )
        self.view_state = SettingsViewStateCoordinator(
            store=store,
            main_window_app=main_window_app,
            tr_func=self._tr,
        )

    def show_divider_color_picker(self):
        self.color_pickers.show_divider_color_picker()

    def show_magnifier_divider_color_picker(self):
        self.color_pickers.show_magnifier_divider_color_picker()

    def show_magnifier_border_color_picker(self):
        self.color_pickers.show_magnifier_border_color_picker()

    def show_laser_color_picker(self):
        self.color_pickers.show_laser_color_picker()

    def show_capture_ring_color_picker(self):
        self.color_pickers.show_capture_ring_color_picker()

    def apply_smart_magnifier_colors(self):
        self.color_pickers.apply_smart_magnifier_colors()

    def update_interpolation_combo_box_ui(self):
        self.view_state.update_interpolation_combo_box_ui()

    def setup_view_buttons(self):
        self.view_state.setup_view_buttons()

    def _tr(self, text):
        return tr(text, self.store.settings.current_language)

    def on_language_changed(self):
        self.update_interpolation_combo_box_ui()
        self.setup_view_buttons()
