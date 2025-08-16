import math
from PyQt6.QtCore import Qt, QPoint, QPointF, pyqtSignal, QObject
from PyQt6.QtGui import QMouseEvent, QKeyEvent

class ImageLabelEventHandler(QObject):
    def __init__(self, app_state, main_controller, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.main_controller = main_controller

    def handle_mouse_press(self, event: QMouseEvent):
        if self.app_state.space_bar_pressed:
            if event.button() == Qt.MouseButton.LeftButton:
                self.main_controller.activate_single_image_mode(1)
            elif event.button() == Qt.MouseButton.RightButton:
                self.main_controller.activate_single_image_mode(2)
            event.accept()
            return

        if (self.app_state.showing_single_image_mode != 0 or
                not self.app_state.original_image1 or not self.app_state.original_image2 or
                self.app_state.resize_in_progress):
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self.app_state.use_magnifier:
                self.app_state.is_dragging_capture_point = True
            else:
                self.app_state.is_dragging_split_line = True

            if hasattr(self.main_controller, 'app') and hasattr(self.main_controller.app, 'event_handler'):
                self.main_controller.app.event_handler.start_interactive_movement()
            elif hasattr(self.parent(), 'main_window_app') and hasattr(self.parent().main_window_app, 'event_handler'):
                self.parent().main_window_app.event_handler.start_interactive_movement()
            self._update_state_from_mouse_position(event.position())
            event.accept()

    def handle_mouse_move(self, event: QMouseEvent):
        if (self.app_state.showing_single_image_mode != 0 or
                self.app_state.resize_in_progress or
                not self.app_state.original_image1 or not self.app_state.original_image2):
            return

        if event.buttons() & Qt.MouseButton.LeftButton and (self.app_state.is_dragging_split_line or self.app_state.is_dragging_capture_point):
            self._update_state_from_mouse_position(event.position())
            event.accept()

    def handle_mouse_release(self, event: QMouseEvent):

        if self.app_state.space_bar_pressed:
            event.accept()
            return

        if self.app_state.showing_single_image_mode != 0:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self.app_state.is_dragging_split_line:
                self.app_state.is_dragging_split_line = False
            if self.app_state.is_dragging_capture_point:
                self.app_state.is_dragging_capture_point = False

            if hasattr(self.main_controller, 'app') and hasattr(self.main_controller.app, 'event_handler'):
                self.main_controller.app.event_handler.stop_interactive_movement()
            elif hasattr(self.parent(), 'main_window_app') and hasattr(self.parent().main_window_app, 'event_handler'):
                self.parent().main_window_app.event_handler.stop_interactive_movement()
            event.accept()

    def handle_key_press(self, event: QKeyEvent):
        self.app_state.pressed_keys.add(event.key())
        if event.key() == Qt.Key.Key_Space:

            if event.isAutoRepeat():
                return
            self.app_state.space_bar_pressed = True

        if hasattr(self.main_controller, 'app') and hasattr(self.main_controller.app, 'event_handler'):
            self.main_controller.app.event_handler.start_interactive_movement()
        elif hasattr(self.parent(), 'main_window_app') and hasattr(self.parent().main_window_app, 'event_handler'):
            self.parent().main_window_app.event_handler.start_interactive_movement()

    def handle_key_release(self, event: QKeyEvent):
        self.app_state.pressed_keys.discard(event.key())
        if event.key() == Qt.Key.Key_Space:

            if event.isAutoRepeat():
                return
            self.app_state.space_bar_pressed = False

            self.main_controller.deactivate_single_image_mode()

    def _update_state_from_mouse_position(self, cursor_pos: QPointF):
        image_rect = self.app_state.image_display_rect_on_label
        if image_rect.isNull() or not image_rect.isValid() or image_rect.width() <= 0 or image_rect.height() <= 0:
            return

        raw_rel_x = (cursor_pos.x() - image_rect.left()) / float(image_rect.width())
        raw_rel_y = (cursor_pos.y() - image_rect.top()) / float(image_rect.height())

        if self.app_state.use_magnifier:
            if not self.app_state.image1: return
            unified_w, unified_h = self.app_state.image1.size
            if unified_w <= 0 or unified_h <= 0: return

            unified_ref_dim = min(unified_w, unified_h)
            capture_size_px = self.app_state.capture_size_relative * unified_ref_dim
            radius_rel_x = (capture_size_px / 2.0) / unified_w if unified_w > 0 else 0
            radius_rel_y = (capture_size_px / 2.0) / unified_h if unified_h > 0 else 0
            clamped_rel_x = max(radius_rel_x, min(raw_rel_x, 1.0 - radius_rel_x))
            clamped_rel_y = max(radius_rel_y, min(raw_rel_y, 1.0 - radius_rel_y))
            self.app_state.capture_position_relative = QPointF(clamped_rel_x, clamped_rel_y)
        else:
            rel_pos = raw_rel_x if not self.app_state.is_horizontal else raw_rel_y
            self.app_state.split_position = max(0.0, min(1.0, rel_pos))
