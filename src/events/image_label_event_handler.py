import logging

from PyQt6.QtCore import QElapsedTimer, QObject, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent

from domain.qt_adapters import color_to_qcolor

from domain.types import Point

logger = logging.getLogger("ImproveImgSLI")

class ImageLabelEventHandler(QObject):
    def __init__(self, store, main_controller, parent=None):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.presenter = parent

        self._mouse_move_timer = QElapsedTimer()
        self._mouse_move_timer.start()

    @property
    def event_bus(self):
        if self.main_controller is not None:
            return self.main_controller.event_bus
        return None

    def handle_mouse_press(self, event: QMouseEvent):
        vp = self.store.viewport
        if vp.space_bar_pressed:
            if (
                event.button() == Qt.MouseButton.LeftButton
                and self.main_controller is not None
                and self.main_controller.session_ctrl is not None
            ):
                self.main_controller.session_ctrl.activate_single_image_mode(1)
            elif (
                event.button() == Qt.MouseButton.RightButton
                and self.main_controller is not None
                and self.main_controller.session_ctrl is not None
            ):
                self.main_controller.session_ctrl.activate_single_image_mode(2)
            event.accept()
            return

        if vp.showing_single_image_mode != 0 or not vp.image1 or vp.resize_in_progress:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if vp.use_magnifier:
                clicked_id = self._get_magnifier_at_position(event.position())
                if clicked_id:
                    vp.active_magnifier_id = clicked_id
                    self.store.emit_state_change()
                    if self.main_controller:
                        self.main_controller.update_requested.emit()

                if not vp.active_magnifier_id:
                    vp.active_magnifier_id = "default"
                    self.store.emit_state_change()

                vp.is_dragging_capture_point = True
                if self.main_controller:
                    self.main_controller.start_interactive_movement.emit()
                self._update_state_from_mouse_position(event.position())
            else:
                vp.is_dragging_split_line = True
                if self.main_controller:
                    self.main_controller.start_interactive_movement.emit()
                self._update_state_from_mouse_position(event.position())
            event.accept()
        elif (
            event.button() == Qt.MouseButton.RightButton
            and vp.use_magnifier
            and vp.is_magnifier_combined
        ):
            is_in_magnifier = self._is_point_in_magnifier(event.position())

            if is_in_magnifier:
                vp.is_dragging_split_in_magnifier = True
                if self.main_controller:
                    self.main_controller.start_interactive_movement.emit()
                self._update_magnifier_internal_split(event.position())
                event.accept()

    def handle_mouse_move(self, event: QMouseEvent):
        vp = self.store.viewport
        if vp.showing_single_image_mode != 0 or vp.resize_in_progress:
            return

        if self._mouse_move_timer.elapsed() < 16:
            return
        self._mouse_move_timer.restart()

        if event.buttons() & Qt.MouseButton.LeftButton and (
            vp.is_dragging_split_line or vp.is_dragging_capture_point
        ):
            self._update_state_from_mouse_position(event.position())
            event.accept()

        if (
            event.buttons() & Qt.MouseButton.RightButton
            and vp.is_dragging_split_in_magnifier
        ):

            self._update_magnifier_internal_split(event.position())
            event.accept()

    def handle_mouse_release(self, event: QMouseEvent):
        vp = self.store.viewport
        if vp.space_bar_pressed:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            vp.is_dragging_split_line = False
            vp.is_dragging_capture_point = False
            self.store.emit_state_change()
            if self.main_controller:
                self.main_controller.stop_interactive_movement.emit()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            vp.is_dragging_split_in_magnifier = False
            self.store.emit_state_change()
            if self.main_controller:
                self.main_controller.stop_interactive_movement.emit()
            event.accept()

    def _get_image_label(self):
        if self.presenter and hasattr(self.presenter, "ui"):
            return getattr(self.presenter.ui, "image_label", None)
        return None

    def _screen_to_image_rel(self, cursor_pos):
        vp = self.store.viewport
        rect = vp.image_display_rect_on_label

        if rect.w <= 0 or rect.h <= 0:
            return None, None

        label = self._get_image_label()
        zoom = 1.0
        pan_x = 0.0
        pan_y = 0.0
        if label is not None:
            zoom = getattr(label, "zoom_level", 1.0)
            pan_x = getattr(label, "pan_offset_x", 0.0)
            pan_y = getattr(label, "pan_offset_y", 0.0)

        w = label.width() if label else 1
        h = label.height() if label else 1

        screen_norm_x = cursor_pos.x() / float(w) if w > 0 else 0.5
        screen_norm_y = cursor_pos.y() / float(h) if h > 0 else 0.5

        uv_x = (screen_norm_x - 0.5) / zoom + 0.5 - pan_x
        uv_y = (screen_norm_y - 0.5) / zoom + 0.5 - pan_y

        img_rel_x = (uv_x * w - rect.x) / float(rect.w)
        img_rel_y = (uv_y * h - rect.y) / float(rect.h)

        return img_rel_x, img_rel_y

    def _update_state_from_mouse_position(self, cursor_pos):
        vp = self.store.viewport

        raw_rel_x, raw_rel_y = self._screen_to_image_rel(cursor_pos)
        if raw_rel_x is None:
            return

        if vp.use_magnifier:

            vp.capture_position_relative = Point(
                max(0.0, min(1.0, raw_rel_x)),
                max(0.0, min(1.0, raw_rel_y)),
            )

            if self.presenter and hasattr(
                self.presenter, "update_capture_area_display"
            ):
                self.presenter.update_capture_area_display()
        else:

            rel_pos = raw_rel_x if not vp.is_horizontal else raw_rel_y
            new_split_pos = max(0.0, min(1.0, rel_pos))

            vp.split_position = new_split_pos

            if (
                vp.is_dragging_split_line
                and self.presenter
                and hasattr(self.presenter, "ui")
            ):

                rect = vp.image_display_rect_on_label
                pixel_pos = 0
                if not vp.is_horizontal:
                    pixel_pos = int(rect.x + (rect.w * new_split_pos))
                else:
                    pixel_pos = int(rect.y + (rect.h * new_split_pos))

                thickness = vp.divider_line_thickness
                color = color_to_qcolor(vp.divider_line_color)

                if hasattr(self.presenter.ui, "image_label"):
                    self.presenter.ui.image_label.set_split_line_params(
                        visible=True,
                        pos=pixel_pos,
                        is_horizontal=vp.is_horizontal,
                        color=color,
                        thickness=thickness,
                    )

        self.store.emit_state_change()

    def _update_magnifier_internal_split(self, position: QPointF):

        vp = self.store.viewport

        center = vp.magnifier_screen_center
        size = vp.magnifier_screen_size

        if size <= 0:
            return

        radius = size / 2.0

        val = 0.5

        if not vp.magnifier_is_horizontal:

            left_edge = center.x - radius

            val = (position.x() - left_edge) / size
        else:

            top_edge = center.y - radius
            val = (position.y() - top_edge) / size

        clamped_val = max(0.0, min(1.0, val))

        if vp.magnifier_internal_split != clamped_val:
            vp.magnifier_internal_split = clamped_val

            self.store.emit_state_change()

            if self.main_controller:
                self.main_controller.update_requested.emit()

    def _is_point_in_magnifier(self, pos: QPointF) -> bool:
        vp = self.store.viewport
        size = vp.magnifier_screen_size
        if size <= 0:
            return False
        center = vp.magnifier_screen_center
        half = size / 2.0

        dx = pos.x() - center.x
        dy = pos.y() - center.y
        distance_squared = dx * dx + dy * dy
        radius_squared = half * half
        is_inside = distance_squared <= radius_squared
        return is_inside

    def _get_magnifier_at_position(self, position: QPointF) -> str | None:
        if self._is_point_in_magnifier(position):
            return self.store.viewport.active_magnifier_id or "default"
        return None

    def handle_key_press(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Space:
            if event.isAutoRepeat():
                return
            self.store.viewport.space_bar_pressed = True
            self.store.emit_state_change()
            event.accept()
            return

        magnifier_keys = {
            Qt.Key.Key_W,
            Qt.Key.Key_A,
            Qt.Key.Key_S,
            Qt.Key.Key_D,
            Qt.Key.Key_Q,
            Qt.Key.Key_E,
        }

        if key in magnifier_keys and self.store.viewport.use_magnifier:

            if self.main_controller:
                self.main_controller.start_interactive_movement.emit()

        self.store.viewport.pressed_keys.add(key)
        self.store.emit_state_change()

    def handle_key_release(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Space:
            if event.isAutoRepeat():
                return
            self.store.viewport.space_bar_pressed = False
            self.store.emit_state_change()
            event.accept()
            return

        self.store.viewport.pressed_keys.discard(key)
        self.store.emit_state_change()

        magnifier_keys = {
            Qt.Key.Key_W,
            Qt.Key.Key_A,
            Qt.Key.Key_S,
            Qt.Key.Key_D,
            Qt.Key.Key_Q,
            Qt.Key.Key_E,
        }

        if (
            self.store.viewport.use_magnifier
            and not any(k in self.store.viewport.pressed_keys for k in magnifier_keys)
            and not (
                self.store.viewport.is_dragging_split_line
                or self.store.viewport.is_dragging_capture_point
                or self.store.viewport.is_dragging_split_in_magnifier
                or self.store.viewport.is_dragging_any_slider
            )
        ):
            if self.main_controller:
                self.main_controller.stop_interactive_movement.emit()

    def handle_wheel_scroll(self, event: QWheelEvent):
        vp = self.store.viewport

        delta = event.angleDelta().y()
        if abs(delta) < 1:
            return

        cursor_pos = event.position()

        raw_rel_x, raw_rel_y = self._screen_to_image_rel(cursor_pos)
        if raw_rel_x is None:
            label_size = (
                self.parent().get_current_label_dimensions()
                if self.parent()
                else (1, 1)
            )
            raw_rel_x = cursor_pos.x() / float(label_size[0])
            raw_rel_y = cursor_pos.y() / float(label_size[1])

        modifiers = event.modifiers()
        sync_scroll = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if sync_scroll:
            if self.main_controller and self.main_controller.session_ctrl:
                self.main_controller.session_ctrl.on_combobox_changed(1, -1, delta)
                self.main_controller.session_ctrl.on_combobox_changed(2, -1, delta)
                event.accept()
        else:

            if vp.showing_single_image_mode != 0:
                image_number = vp.showing_single_image_mode
            else:
                rel_pos = raw_rel_x if not vp.is_horizontal else raw_rel_y
                image_number = 1 if rel_pos < vp.split_position_visual else 2

            if self.main_controller and self.main_controller.session_ctrl:
                self.main_controller.session_ctrl.on_combobox_changed(
                    image_number, -1, delta
                )
                event.accept()
