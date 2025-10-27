from PyQt6.QtCore import QObject, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent

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

        elif event.button() == Qt.MouseButton.RightButton:

            if self.app_state.use_magnifier and self.app_state.is_magnifier_combined:

                if self._is_point_in_magnifier(event.position()):
                    self.app_state.is_dragging_split_in_magnifier = True
                    if hasattr(self.main_controller, 'app') and hasattr(self.main_controller.app, 'event_handler'):
                        self.main_controller.app.event_handler.start_interactive_movement()
                    elif hasattr(self.parent(), 'main_window_app') and hasattr(self.parent().main_window_app, 'event_handler'):
                        self.parent().main_window_app.event_handler.start_interactive_movement()
                    self._update_magnifier_internal_split(event.position())
                    event.accept()

    def handle_mouse_move(self, event: QMouseEvent):
        if (self.app_state.showing_single_image_mode != 0 or
                self.app_state.resize_in_progress or
                not self.app_state.original_image1 or not self.app_state.original_image2):
            return

        if event.buttons() & Qt.MouseButton.LeftButton and (self.app_state.is_dragging_split_line or self.app_state.is_dragging_capture_point):
            self._update_state_from_mouse_position(event.position())
            event.accept()

        if event.buttons() & Qt.MouseButton.RightButton and self.app_state.is_dragging_split_in_magnifier:
            self._update_magnifier_internal_split(event.position())
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

        elif event.button() == Qt.MouseButton.RightButton:
            if self.app_state.is_dragging_split_in_magnifier:
                self.app_state.is_dragging_split_in_magnifier = False

                if hasattr(self.main_controller, 'app') and hasattr(self.main_controller.app, 'event_handler'):
                    self.main_controller.app.event_handler.stop_interactive_movement()
                elif hasattr(self.parent(), 'main_window_app') and hasattr(self.parent().main_window_app, 'event_handler'):
                    self.parent().main_window_app.event_handler.stop_interactive_movement()
                event.accept()

    def handle_key_press(self, event: QKeyEvent):

        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if not event.isAutoRepeat():
                self.main_controller.paste_image_from_clipboard()
            return

        if event.key() == Qt.Key.Key_S:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if not event.isAutoRepeat():
                    self.main_controller.presenter._quick_save_with_error_handling()
                return
            elif event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
                if not event.isAutoRepeat():
                    self.main_controller.presenter._save_result_with_error_handling()
                return

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

    def handle_wheel_scroll(self, event: QWheelEvent):

        if self.app_state.use_magnifier or (not self.app_state.image_list1 and not self.app_state.image_list2):
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        direction = 1 if delta < 0 else -1

        pos = event.position()
        rect = self.app_state.image_display_rect_on_label

        if not rect.contains(pos.toPoint()):
            return

        if not self.app_state.is_horizontal:
            split_x = rect.left() + rect.width() * self.app_state.split_position_visual
            image_number = 2 if pos.x() > split_x else 1
        else:
            split_y = rect.top() + rect.height() * self.app_state.split_position_visual
            image_number = 2 if pos.y() > split_y else 1

        if image_number == 1:
            current_index = self.app_state.current_index1
            count = len(self.app_state.image_list1)
        else:
            current_index = self.app_state.current_index2
            count = len(self.app_state.image_list2)

        if count <= 1:
            return

        new_index = (current_index + direction + count) % count

        self.main_controller.on_combobox_changed(image_number, new_index)
        event.accept()

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

    def _is_point_in_magnifier(self, cursor_pos: QPointF) -> bool:
        if not self.app_state.magnifier_screen_center or self.app_state.magnifier_screen_size <= 0:
            return False

        dx = cursor_pos.x() - self.app_state.magnifier_screen_center.x()
        dy = cursor_pos.y() - self.app_state.magnifier_screen_center.y()
        distance_sq = dx * dx + dy * dy

        radius = self.app_state.magnifier_screen_size / 2.0
        return distance_sq <= radius * radius

    def _update_magnifier_internal_split(self, cursor_pos: QPointF):
        if not self.app_state.magnifier_screen_center or self.app_state.magnifier_screen_size <= 0:
            return

        mag_center = self.app_state.magnifier_screen_center
        mag_size = self.app_state.magnifier_screen_size

        if not self.app_state.magnifier_is_horizontal:
            left_edge = mag_center.x() - mag_size / 2.0

            rel_pos = (cursor_pos.x() - left_edge) / mag_size if mag_size > 0 else 0.5
            self.app_state.magnifier_internal_split = max(0.0, min(1.0, rel_pos))
        else:
            top_edge = mag_center.y() - mag_size / 2.0

            rel_pos = (cursor_pos.y() - top_edge) / mag_size if mag_size > 0 else 0.5
            self.app_state.magnifier_internal_split = max(0.0, min(1.0, rel_pos))

        if hasattr(self.main_controller, 'presenter') and self.main_controller.presenter:
            self.main_controller.presenter.main_window_app.schedule_update()

