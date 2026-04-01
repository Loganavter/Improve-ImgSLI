import logging

from PyQt6.QtCore import QObject, pyqtSignal

from core.store import Store
from ui.presenters.image_canvas.runtime import (
    build_image_canvas_components,
    connect_image_canvas_runtime,
)

logger = logging.getLogger("ImproveImgSLI")

class ImageCanvasPresenter(QObject):

    _worker_finished_signal = pyqtSignal(dict, dict, int)
    _worker_error_signal = pyqtSignal(str)

    def __init__(self, store: Store, main_controller, ui, main_window_app, parent=None):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.ui = ui
        self.main_window_app = main_window_app
        components = build_image_canvas_components(self)
        self.lifecycle = components.lifecycle
        self.view = components.view
        self.background = components.background
        self.magnifier = components.magnifier
        self.results = components.results
        self.lifecycle.initialize()
        connect_image_canvas_runtime(self)

    def _on_action(self, action):
        from core.state_management.actions import UpdateMagnifierCombinedStateAction
        if isinstance(action, UpdateMagnifierCombinedStateAction):
            self._last_mag_signature = None

    def connect_event_handler_signals(self, event_handler):
        return self.lifecycle.connect_event_handler_signals(event_handler)

    def get_current_label_dimensions(self) -> tuple[int, int]:
        return self.lifecycle.get_current_label_dimensions()

    def update_minimum_window_size(self):
        return self.lifecycle.update_minimum_window_size()

    def schedule_update(self):
        return self.background.schedule_update()

    def invalidate_render_state(self, clear_magnifier: bool = False):
        return self.lifecycle.invalidate_render_state(clear_magnifier)

    def update_comparison_if_needed(self) -> bool:
        return self.background.update_comparison_if_needed()

    def start_interactive_movement(self):
        return self.lifecycle.start_interactive_movement()

    def stop_interactive_movement(self):
        return self.magnifier.stop_interactive_movement()

    def update_capture_area_display(self):
        return self.magnifier.update_capture_area_display()
