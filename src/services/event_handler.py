from services.state_manager import AppConstants
import importlib
import os
import sys
import math
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox, QLineEdit, QComboBox
from PyQt6.QtCore import Qt, QPoint, QPointF, QEvent, QTimer, QElapsedTimer, QByteArray, QObject
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QMouseEvent
import logging

logger = logging.getLogger("ImproveImgSLI")

translations_mod = importlib.import_module('translations')
tr = getattr(
    translations_mod,
    'tr',
    lambda text,
    lang='en',
    *args,
    **kwargs: text)

MAGNIFIER_CONTROL_KEYS = {
    Qt.Key.Key_W.value,
    Qt.Key.Key_A.value,
    Qt.Key.Key_S.value,
    Qt.Key.Key_D.value,
    Qt.Key.Key_Q.value,
    Qt.Key.Key_E.value}


class EventHandler(QObject):
    def __init__(self, app_instance, app_state, ui_logic):
        super().__init__(app_instance)
        self.app = app_instance
        self.app_state = app_state
        self.ui_logic = ui_logic
        self.main_controller = app_instance.main_controller

        self.movement_timer = QTimer(self)
        self.movement_timer.setInterval(16)
        self.movement_timer.timeout.connect(self._handle_interactive_movement_and_lerp)
        self.movement_elapsed_timer = QElapsedTimer()
        self.last_update_elapsed = 0

        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._finish_resize)

        if hasattr(self.app, 'image_label') and self.app.image_label is not None:
            if hasattr(self.app.image_label, 'mousePressed'):
                self.app.image_label.mousePressed.connect(self.handle_mouse_press)
            if hasattr(self.app.image_label, 'mouseMoved'):
                self.app.image_label.mouseMoved.connect(self.handle_mouse_move)
            if hasattr(self.app.image_label, 'mouseReleased'):
                self.app.image_label.mouseReleased.connect(self.handle_mouse_release)

    def eventFilter(self, watched_obj, event: QEvent) -> bool:
        event_type = event.type()
        
        if event_type == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Space and not event.isAutoRepeat():
                if not isinstance(QApplication.focusWidget(), QLineEdit):
                    self.app_state.space_bar_pressed = True
                    buttons = QApplication.mouseButtons()
                    if buttons & Qt.MouseButton.LeftButton:
                        self.main_controller.activate_single_image_mode(1)
                    elif buttons & Qt.MouseButton.RightButton:
                        self.main_controller.activate_single_image_mode(2)
                    return True
            
            if self.app_state.use_magnifier and self.app_state.showing_single_image_mode == 0 and \
               key in MAGNIFIER_CONTROL_KEYS and not event.isAutoRepeat():
                if not isinstance(QApplication.focusWidget(), QLineEdit):
                    self.app_state.pressed_keys.add(key)
                    self._enter_interactive_mode()
                    return True

        elif event_type == QEvent.Type.KeyRelease:
            key = event.key()
            if key == Qt.Key.Key_Space and not event.isAutoRepeat():
                if self.app_state.space_bar_pressed:
                    self.app_state.space_bar_pressed = False
                    if self.app_state.showing_single_image_mode != 0:
                        self.main_controller.deactivate_single_image_mode()
                    return True
            
            if key in self.app_state.pressed_keys and not event.isAutoRepeat():
                self.app_state.pressed_keys.remove(key)
                self._handle_interactive_movement_and_lerp() 
                return True

        return super().eventFilter(watched_obj, event)

    def handle_mouse_press(self, event: QMouseEvent):
        if self.app_state.space_bar_pressed:
            if event.button() == Qt.MouseButton.LeftButton:
                self.main_controller.activate_single_image_mode(1)
            elif event.button() == Qt.MouseButton.RightButton:
                self.main_controller.activate_single_image_mode(2)
            event.accept()
            return
            
        if self.app_state.showing_single_image_mode != 0 or not self.app_state.original_image1 or \
           not self.app_state.original_image2 or self.app_state.resize_in_progress:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self._enter_interactive_mode()
            if self.app_state.use_magnifier:
                self.app_state.is_dragging_capture_point = True
            else:
                self.app_state.is_dragging_split_line = True
            
            self._update_state_from_mouse_position(event.position())
            event.accept()

    def handle_mouse_move(self, event: QMouseEvent):
        if self.app_state.showing_single_image_mode != 0 or self.app_state.resize_in_progress or \
           not self.app_state.original_image1 or not self.app_state.original_image2:
            return

        if event.buttons() & Qt.MouseButton.LeftButton and \
           (self.app_state.is_dragging_split_line or self.app_state.is_dragging_capture_point):
            
            self._update_state_from_mouse_position(event.position())
            event.accept()
            
    def handle_mouse_release(self, event: QMouseEvent):
        if self.app_state.space_bar_pressed and event.button() in [Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton]:
            if not self.app_state.space_bar_pressed:
                 self.main_controller.deactivate_single_image_mode()
            event.accept()
            return

        if self.app_state.showing_single_image_mode != 0:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self.app_state.is_dragging_split_line:
                self.app_state.is_dragging_split_line = False
                self.app.settings_manager._save_setting('split_position', self.app_state.split_position)
            if self.app_state.is_dragging_capture_point:
                self.app_state.is_dragging_capture_point = False
                self.app.settings_manager._save_setting('capture_relative_x', self.app_state.capture_position_relative.x())
                self.app.settings_manager._save_setting('capture_relative_y', self.app_state.capture_position_relative.y())

            self._handle_interactive_movement_and_lerp()
            event.accept()

    def _update_state_from_mouse_position(self, cursor_pos_f: QPointF):
        image_rect = self.app_state.image_display_rect_on_label
        if image_rect.isNull() or not image_rect.isValid() or image_rect.width() <= 0 or image_rect.height() <= 0:
            return

        raw_rel_x = (cursor_pos_f.x() - image_rect.left()) / float(image_rect.width())
        raw_rel_y = (cursor_pos_f.y() - image_rect.top()) / float(image_rect.height())

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

    def handle_drag_enter(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.ui_logic._update_drag_overlays(self.app_state.is_horizontal)
            self.app.drag_overlay1.setText(tr('Drop Image(s) 1 Here', self.app_state.current_language))
            self.app.drag_overlay2.setText(tr('Drop Image(s) 2 Here', self.app_state.current_language))
            self.app.drag_overlay1.show()
            self.app.drag_overlay2.show()
        else:
            event.ignore()

    def handle_drag_move(self, event: QDragMoveEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def handle_drag_leave(self, event: QEvent):
        self.app.drag_overlay1.hide()
        self.app.drag_overlay2.hide()
        event.accept()

    def handle_drop(self, event: QDropEvent):
        self.app.drag_overlay1.hide()
        self.app.drag_overlay2.hide()
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            image_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
            if not image_paths:
                event.ignore()
                return

            drop_pos = event.position().toPoint()
            is_left = self._is_in_left_area(drop_pos)
            logger.debug(f"Drop at window coordinates {drop_pos}. Is in left area: {is_left}.")

            if is_left:
                logger.debug(f'Routing drop to slot 1.')
                self.main_controller.load_images_from_paths(image_paths, 1)
            else:
                logger.debug(f'Routing drop to slot 2.')
                self.main_controller.load_images_from_paths(image_paths, 2)
            event.acceptProposedAction()
        else:
            event.ignore()

    def handle_resize_event(self, event):
        if not self.app_state.resize_in_progress:
            self.app_state.resize_in_progress = True
        self.ui_logic._update_drag_overlays(self.app_state.is_horizontal)
        self.resize_timer.start(200)

    def _finish_resize(self):
        if self.app_state.resize_in_progress:
            self.app_state.resize_in_progress = False
            logger.debug("Resize finished, emitting stateChanged signal for redraw.")
            self.app_state.stateChanged.emit()

    def handle_change_event(self, event: QEvent):
        if event.type() == QEvent.Type.LanguageChange:
            self.app.ui_logic.update_translations()
        elif event.type() == QEvent.Type.WindowStateChange:
            pass

    def handle_close_event(self, event):
        self.app.thread_pool.waitForDone()
        self.app.settings_manager.save_all_settings(self.app_state, self.app)
    
    def _enter_interactive_mode(self):
        if not self.app_state.is_interactive_mode:
            self.app_state.is_interactive_mode = True
            self.app_state.clear_all_caches()

        if not self.movement_timer.isActive():
            self.movement_elapsed_timer.start()
            self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
            self.movement_timer.start()

    def _exit_interactive_mode(self):
        if self.movement_timer.isActive():
            self.movement_timer.stop()
        
        if self.app_state.is_interactive_mode:
            self.app_state.is_interactive_mode = False
            logger.debug("Exiting interactive mode, emitting stateChanged for final render.")
            self.app_state.stateChanged.emit()

    def _handle_interactive_movement_and_lerp(self):
        if self.app_state.showing_single_image_mode != 0:
            if self.movement_timer.isActive():
                self.movement_timer.stop()
            return

        delta_time_ms = self.movement_elapsed_timer.elapsed() - self.last_update_elapsed
        if delta_time_ms <= 0: return
        
        self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
        delta_time_sec = delta_time_ms / 1000.0
        if self.app_state.use_magnifier and self.app_state.pressed_keys:
            dx_dir = (Qt.Key.Key_D.value in self.app_state.pressed_keys) - (Qt.Key.Key_A.value in self.app_state.pressed_keys)
            dy_dir = (Qt.Key.Key_S.value in self.app_state.pressed_keys) - (Qt.Key.Key_W.value in self.app_state.pressed_keys)
            ds_dir = (Qt.Key.Key_E.value in self.app_state.pressed_keys) - (Qt.Key.Key_Q.value in self.app_state.pressed_keys)

            speed_factor = self.app_state.movement_speed_per_sec * AppConstants.BASE_MOVEMENT_SPEED
            
            if dx_dir != 0 or dy_dir != 0:
                length = math.sqrt(dx_dir**2 + dy_dir**2)
                if length > 1.0:
                    dx_dir /= length
                    dy_dir /= length
                
                delta_x = dx_dir * speed_factor * delta_time_sec
                delta_y = dy_dir * speed_factor * delta_time_sec
                
                if self.app_state.freeze_magnifier and self.app_state.frozen_magnifier_absolute_pos:
                    drawing_width, drawing_height = self.app_state.pixmap_width, self.app_state.pixmap_height
                    target_max_dim_drawing = float(max(drawing_width, drawing_height))
                    
                    delta_pixels_x = delta_x * target_max_dim_drawing
                    delta_pixels_y = delta_y * target_max_dim_drawing
                    
                    new_frozen_pos_pixels = self.app_state.frozen_magnifier_absolute_pos + QPoint(
                        int(round(delta_pixels_x)),
                        int(round(delta_pixels_y))
                    )
                    self.app_state.frozen_magnifier_absolute_pos = new_frozen_pos_pixels
                else:
                    new_offset = self.app_state.magnifier_offset_relative + QPointF(delta_x, delta_y)
                    self.app_state.magnifier_offset_relative = new_offset

            if ds_dir != 0:
                delta_spacing = ds_dir * speed_factor * delta_time_sec
                new_spacing = self.app_state.magnifier_spacing_relative + delta_spacing
                self.app_state.magnifier_spacing_relative = max(0.0, min(0.5, new_spacing))
        
        if not self.app_state.freeze_magnifier:
            self.app_state.magnifier_offset_relative_visual = self._lerp_vector(
                self.app_state.magnifier_offset_relative_visual,
                self.app_state.magnifier_offset_relative,
                AppConstants.SMOOTHING_FACTOR_POS
            )
        else:
            pass

        self.app_state.magnifier_spacing_relative_visual = self._lerp_scalar(
            self.app_state.magnifier_spacing_relative_visual,
            self.app_state.magnifier_spacing_relative,
            AppConstants.SMOOTHING_FACTOR_SPACING
        )

        self.app_state.split_position_visual = self._lerp_scalar(
            self.app_state.split_position_visual,
            self.app_state.split_position,
            AppConstants.SMOOTHING_FACTOR_SPLIT
        )

        self.app_state.stateChanged.emit()

        is_still_interacting = (
            self.app_state.is_dragging_split_line or
            self.app_state.is_dragging_capture_point or
            self.app_state.is_dragging_any_slider or
            bool(self.app_state.pressed_keys)
        )
        
        is_still_lerping_magnifier = False
        if not self.app_state.freeze_magnifier:
            is_still_lerping_magnifier = (
                not self._is_close(self.app_state.magnifier_offset_relative_visual, self.app_state.magnifier_offset_relative) or
                not math.isclose(self.app_state.magnifier_spacing_relative_visual, self.app_state.magnifier_spacing_relative, abs_tol=AppConstants.LERP_STOP_THRESHOLD)
            )

        is_still_lerping_split = not math.isclose(self.app_state.split_position_visual, self.app_state.split_position, abs_tol=AppConstants.LERP_STOP_THRESHOLD)

        if not is_still_interacting and not is_still_lerping_magnifier and not is_still_lerping_split:
            self._exit_interactive_mode()

    def _lerp_scalar(self, current, target, factor):
        return current + (target - current) * factor
    
    def _lerp_vector(self, current, target, factor):
        return QPointF(
            self._lerp_scalar(current.x(), target.x(), factor),
            self._lerp_scalar(current.y(), target.y(), factor)
        )

    def _is_close(self, p1, p2):
        return math.isclose(p1.x(), p2.x(), abs_tol=AppConstants.LERP_STOP_THRESHOLD) and \
               math.isclose(p1.y(), p2.y(), abs_tol=AppConstants.LERP_STOP_THRESHOLD)

    def _is_in_left_area(self, pos: QPoint) -> bool:
        if not hasattr(self.app, 'image_label') or not self.app.image_label.isVisible():
            return True

        label_rect = self.app.image_label.geometry()

        if not self.app_state.is_horizontal:
            center_x = label_rect.x() + label_rect.width() / 2
            return pos.x() < center_x
        else:
            center_y = label_rect.y() + label_rect.height() / 2
            return pos.y() < center_y