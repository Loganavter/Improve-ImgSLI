from PyQt6.QtCore import QObject

from core.store import Store
from ui.presenters.toolbar.connections import connect_signals as connect_signals_impl
from ui.presenters.toolbar.state import (
    check_name_lengths,
    update_toolbar_states,
)
from ui.presenters.toolbar.orientation import update_magnifier_orientation_button_state

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

    def update_magnifier_orientation_button_state(self):
        return update_magnifier_orientation_button_state(self)

    def check_name_lengths(self):
        return check_name_lengths(self)

    def update_toolbar_states(self):
        return update_toolbar_states(self)
