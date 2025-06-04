import importlib
import os
import sys
import math
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox, QLineEdit, QComboBox
from PyQt6.QtCore import Qt, QPoint, QPointF, QEvent, QTimer, QElapsedTimer, QByteArray, QObject
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
translations_mod = importlib.import_module('translations')
tr = getattr(translations_mod, 'tr', lambda text, lang='en', *args, **kwargs: text)
from services.state_manager import AppConstants
MAGNIFIER_CONTROL_KEYS = {Qt.Key.Key_W.value, Qt.Key.Key_A.value, Qt.Key.Key_S.value, Qt.Key.Key_D.value, Qt.Key.Key_Q.value, Qt.Key.Key_E.value}

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
        self.interactive_update_timer = QTimer(self)
        self.interactive_update_timer.setSingleShot(True)
        self.interactive_update_timer.setInterval(30)
        self.interactive_update_timer.timeout.connect(self._perform_interactive_update)
        self.pending_interactive_update = False
        if hasattr(self.app, 'image_label') and self.app.image_label is not None:
            if hasattr(self.app.image_label, 'mousePressed'):
                self.app.image_label.mousePressed.connect(self.handle_mouse_press)
            if hasattr(self.app.image_label, 'mouseMoved'):
                self.app.image_label.mouseMoved.connect(self.handle_mouse_move)
            if hasattr(self.app.image_label, 'mouseReleased'):
                self.app.image_label.mouseReleased.connect(self.handle_mouse_release)

    def _request_interactive_update(self):
        self.pending_interactive_update = True
        if not self.interactive_update_timer.isActive():
            self.interactive_update_timer.start()

    def _perform_interactive_update(self):
        if self.pending_interactive_update:
            self.pending_interactive_update = False
            if self.app_state.is_interactive_mode:
                try:
                    self.app.update_comparison_if_needed()
                except Exception as e:
                    print(f'ERROR: _perform_interactive_update: {e}')
                    traceback.print_exc()

    def eventFilter(self, watched_obj, event: QEvent) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.KeyPress:
            key = event.key()
            is_modifier = key in (Qt.Key.Key_Shift.value, Qt.Key.Key_Control.value, Qt.Key.Key_Alt.value, Qt.Key.Key_Meta.value)
            if key == Qt.Key.Key_Space.value and (not event.isAutoRepeat()):
                focused_widget = QApplication.focusWidget()
                if isinstance(focused_widget, QLineEdit):
                    return False
                print('DEBUG: Space bar pressed.')
                self.app_state.space_bar_pressed = True
                app_instance_qt = QApplication.instance()
                buttons = app_instance_qt.mouseButtons() if app_instance_qt else Qt.MouseButton.NoButton
                if buttons == Qt.MouseButton.LeftButton:
                    print('DEBUG: Space + Left Mouse detected for quick preview 1.')
                    self.main_controller.activate_single_image_mode(1)
                elif buttons == Qt.MouseButton.RightButton:
                    print('DEBUG: Space + Right Mouse detected for quick preview 2.')
                    self.main_controller.activate_single_image_mode(2)
                return True
            if self.app_state.use_magnifier and self.app_state.showing_single_image_mode == 0 and (key in MAGNIFIER_CONTROL_KEYS) and (not event.isAutoRepeat()) and (not is_modifier):
                focused_widget = QApplication.focusWidget()
                if isinstance(focused_widget, QLineEdit):
                    return False
                if isinstance(focused_widget, QComboBox) and focused_widget.isEditable():
                    if focused_widget.lineEdit() and focused_widget.lineEdit().hasFocus():
                        return False
                print(f'DEBUG: Magnifier control key {key} pressed.')
                self.app_state.pressed_keys.add(key)
                self._enter_interactive_mode()
                return True
        elif event_type == QEvent.Type.KeyRelease:
            key = event.key()
            is_modifier = key in (Qt.Key.Key_Shift.value, Qt.Key.Key_Control.value, Qt.Key.Key_Alt.value, Qt.Key.Key_Meta.value)
            if key == Qt.Key.Key_Space.value and (not event.isAutoRepeat()):
                print('DEBUG: Space bar released.')
                if self.app_state.space_bar_pressed:
                    self.app_state.space_bar_pressed = False
                    if self.app_state.showing_single_image_mode != 0:
                        print('DEBUG: Deactivating single image mode after space release.')
                        self.main_controller.deactivate_single_image_mode()
                    return True
                focused_widget = QApplication.focusWidget()
                if isinstance(focused_widget, QLineEdit):
                    return False
            if not event.isAutoRepeat() and (not is_modifier) and (key in self.app_state.pressed_keys):
                self.app_state.pressed_keys.remove(key)
                self._handle_interactive_movement_and_lerp()
                return True
        return False

    def handle_mouse_press(self, event):
        print(f'DEBUG_PRESS_EVENT: Pos={event.position().x():.1f},{event.position().y():.1f}, Button={event.button()}')
        if self.app_state.space_bar_pressed:
            if event.button() == Qt.MouseButton.LeftButton:
                print('DEBUG: Space + Left mouse press for quick preview 1.')
                self.main_controller.activate_single_image_mode(1)
                event.accept()
                return
            elif event.button() == Qt.MouseButton.RightButton:
                print('DEBUG: Space + Right mouse press for quick preview 2.')
                self.main_controller.activate_single_image_mode(2)
                event.accept()
                return
        if self.app_state.showing_single_image_mode != 0:
            event.accept()
            return
        if not self.app_state.original_image1 or not self.app_state.original_image2:
            return
        if self.app_state.resize_in_progress:
            return
        self._enter_interactive_mode()
        pos_f = event.position()
        if event.button() == Qt.MouseButton.LeftButton:
            if self.app_state.use_magnifier:
                self.app_state.is_dragging_capture_point = True
                print('DEBUG: Started dragging capture point.')
                self.app_state.clear_magnifier_cache()
                print('DEBUG: Magnifier cache cleared.')
                self.main_controller.update_split_or_capture_position_only_state(pos_f)
                self._request_interactive_update()
                event.accept()
            else:
                self.app_state.is_dragging_split_line = True
                self.app_state.split_is_actively_lerping = True
                print('DEBUG: Started dragging split line.')
                self.app_state.clear_split_cache()
                print('DEBUG: Split cache cleared.')
                self.main_controller.update_split_or_capture_position_only_state(pos_f)
                self._request_interactive_update()
                event.accept()

    def handle_mouse_move(self, event):
        pos_f = event.position()
        if self.app_state.showing_single_image_mode != 0:
            event.accept()
            return
        if self.app_state.resize_in_progress or not self.app_state.original_image1 or (not self.app_state.original_image2):
            return
        if not event.buttons() & Qt.MouseButton.LeftButton:
            return
        if not (self.app_state.is_dragging_split_line or self.app_state.is_dragging_capture_point):
            return
        needs_state_update = False
        label_width, label_height = self.app.get_current_label_dimensions()
        if label_width <= 0 or label_height <= 0 or self.app_state.pixmap_width <= 0 or (self.app_state.pixmap_height <= 0):
            return
        label_rect = self.app.image_label.contentsRect()
        x_offset = max(0, (label_rect.width() - self.app_state.pixmap_width) // 2)
        y_offset = max(0, (label_rect.height() - self.app_state.pixmap_height) // 2)
        pixmap_x_f, pixmap_y_f = (pos_f.x() - label_rect.x() - x_offset, pos_f.y() - label_rect.y() - y_offset)
        pixmap_x_clamped = max(0.0, min(float(self.app_state.pixmap_width), pixmap_x_f))
        pixmap_y_clamped = max(0.0, min(float(self.app_state.pixmap_height), pixmap_y_f))
        rel_x = pixmap_x_clamped / float(self.app_state.pixmap_width) if self.app_state.pixmap_width > 0 else 0.5
        rel_y = pixmap_y_clamped / float(self.app_state.pixmap_height) if self.app_state.pixmap_height > 0 else 0.5
        rel_x, rel_y = (max(0.0, min(1.0, rel_x)), max(0.0, min(1.0, rel_y)))
        epsilon = 1e-06
        if self.app_state.use_magnifier:
            if self.app_state.is_dragging_capture_point:
                new_capture_pos = QPointF(rel_x, rel_y)
                current_capture_pos = self.app_state.capture_position_relative
                if abs(current_capture_pos.x() - new_capture_pos.x()) > epsilon or abs(current_capture_pos.y() - new_capture_pos.y()) > epsilon:
                    self.app_state.capture_position_relative = new_capture_pos
                    self.app_state.clear_magnifier_cache()
                    needs_state_update = True
                event.accept()
        elif self.app_state.is_dragging_split_line:
            new_split_pos = rel_x if not self.app_state.is_horizontal else rel_y
            if abs(self.app_state.split_position - new_split_pos) > epsilon:
                self.app_state.split_position = new_split_pos
                self.app_state.split_is_actively_lerping = True
                needs_state_update = True
            event.accept()
        if needs_state_update and self.app_state.showing_single_image_mode == 0:
            self._request_interactive_update()

    def handle_mouse_release(self, event):
        print(f'DEBUG_RELEASE_EVENT: Pos={event.position().x():.1f},{event.position().y():.1f}, Button={event.button()}, is_dragging_split_line={self.app_state.is_dragging_split_line}, is_dragging_capture_point={self.app_state.is_dragging_capture_point}')
        mouse_button_released_for_single_mode = False
        if self.app_state.showing_single_image_mode == 1 and event.button() == Qt.MouseButton.LeftButton:
            print('DEBUG: Mouse release (left) in single image 1 preview.')
            mouse_button_released_for_single_mode = True
        elif self.app_state.showing_single_image_mode == 2 and event.button() == Qt.MouseButton.RightButton:
            print('DEBUG: Mouse release (right) in single image 2 preview.')
            mouse_button_released_for_single_mode = True
        if mouse_button_released_for_single_mode:
            if not self.app_state.space_bar_pressed:
                print('DEBUG: Deactivating single image mode after mouse release (space not pressed).')
                self.main_controller.deactivate_single_image_mode()
            else:
                print('DEBUG: Space bar still pressed, keeping single image mode active.')
            event.accept()
            return
        if self.app_state.showing_single_image_mode != 0:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self.app_state.is_dragging_split_line:
                print(f'DEBUG_RELEASE_EVENT: Left mouse released. Current split_position BEFORE setting is_dragging_split_line=False: {self.app_state.split_position:.4f}')
                self.app_state.is_dragging_split_line = False
                self.app_state.split_is_actively_lerping = True
                print('DEBUG_RELEASE_EVENT: is_dragging_split_line set to False. split_is_actively_lerping set to True.')
                self.main_controller.update_split_or_capture_position_only_state(event.position())
                self._handle_interactive_movement_and_lerp()
            if self.app_state.is_dragging_capture_point:
                self.app_state.is_dragging_capture_point = False
                print('DEBUG: Stopped dragging capture point.')
                self.app.settings_manager._save_setting('capture_relative_x', self.app_state.capture_position_relative.x())
                self.app.settings_manager._save_setting('capture_relative_y', self.app_state.capture_position_relative.y())
                print('DEBUG: Capture position saved to settings.')
                self._handle_interactive_movement_and_lerp()
            event.accept()

    def handle_drag_enter(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.ui_logic._update_drag_overlays(self.app_state.is_horizontal)
            if self.app_state.original_image1 is None:
                self.app.drag_overlay1.setText(tr('Drop Image(s) 1 Here', self.app_state.current_language))
                self.app.drag_overlay1.show()
            if self.app_state.original_image2 is None:
                self.app.drag_overlay2.setText(tr('Drop Image(s) 2 Here', self.app_state.current_language))
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
            image_paths = []
            non_local_files_skipped = []
            unsupported_files_skipped = []
            supported_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff']
            for url in urls:
                if url.isLocalFile():
                    local_path = url.toLocalFile()
                    _, ext = os.path.splitext(local_path)
                    if ext.lower() in supported_extensions:
                        image_paths.append(local_path)
                    else:
                        unsupported_files_skipped.append(f'{os.path.basename(local_path)} ({ext})')
                else:
                    non_local_files_skipped.append(url.toString())
            if not image_paths:
                warning_messages = []
                if non_local_files_skipped:
                    warning_messages.append(self.app.tr('Non-local files skipped:', self.app_state.current_language) + '\n' + '\n'.join(non_local_files_skipped))
                if unsupported_files_skipped:
                    warning_messages.append(self.app.tr('Unsupported files skipped:', self.app_state.current_language) + '\n' + '\n'.join(unsupported_files_skipped))
                if not warning_messages:
                    warning_messages.append(self.app.tr('No supported local image files detected.', self.app_state.current_language))
                QMessageBox.warning(self.app, self.app.tr('Error processing path', self.app_state.current_language), '\n\n'.join(warning_messages))
                event.ignore()
                return
            drop_pos = event.position().toPoint()
            if self._is_in_left_area(drop_pos):
                print(f'DEBUG: Dropped into left area. Loading {len(image_paths)} images for slot 1.')
                self.main_controller.load_images_from_paths(image_paths, 1)
            else:
                print(f'DEBUG: Dropped into right area. Loading {len(image_paths)} images for slot 2.')
                self.main_controller.load_images_from_paths(image_paths, 2)
            event.acceptProposedAction()
        else:
            print('DEBUG: Dropped item has no URLs.')
            event.ignore()

    def handle_resize_event(self, event):
        if not self.app_state.resize_in_progress:
            self.app_state.resize_in_progress = True
        self.ui_logic._update_drag_overlays(self.app_state.is_horizontal)
        self.resize_timer.start(200)

    def _finish_resize(self):
        print('DEBUG: _finish_resize called.')
        if self.app_state.resize_in_progress:
            self.app_state.resize_in_progress = False
            print('DEBUG: Setting resize_in_progress to False. Triggering comparison update.')
            self.app._stabilize_ui_layout()
            self._exit_interactive_mode_if_settled(force_redraw=True)

    def handle_change_event(self, event: QEvent):
        event_type = event.type()
        if event_type == QEvent.Type.LanguageChange:
            print('DEBUG: LanguageChange event detected. Updating translations.')
            self.app.ui_logic.update_translations()
            if hasattr(self.app, 'length_warning_label'):
                self.app.ui_logic.check_name_lengths()
            if hasattr(self.app, 'help_button'):
                self.app.help_button.setToolTip(tr('Show Help', self.app_state.current_language))
            if hasattr(self.app, 'slider_speed'):
                self.app.slider_speed.setToolTip(f"{self.app_state.movement_speed_per_sec:.1f} {tr('rel. units/sec', self.app_state.current_language)}")
            self.app._update_color_button_tooltip()
            if self.app_state.include_file_names_in_saved and self.app_state.showing_single_image_mode == 0:
                print('DEBUG: Triggering comparison update after LanguageChange (file names checked).')
                self._exit_interactive_mode_if_settled(force_redraw=True)
        elif event_type == QEvent.Type.WindowStateChange:
            print('DEBUG: WindowStateChange event detected.')
            old_state_bit = event.oldState() if hasattr(event, 'oldState') else self.app.windowState()
            new_state_bit = self.app.windowState()
            was_max_or_full = bool(old_state_bit & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen))
            is_max_or_full = bool(new_state_bit & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen))
            if is_max_or_full and (not was_max_or_full):
                print('DEBUG: Window maximized/fullscreen from normal state.')
                if self.app_state.loaded_previous_geometry.isNull() or self.app_state.loaded_previous_geometry.isEmpty():
                    current_normal_geom = self.app.saveGeometry()
                    if current_normal_geom and (not current_normal_geom.isEmpty()):
                        self.app_state.loaded_previous_geometry = current_normal_geom
                        print('DEBUG: Saved current normal geometry as previous.')
            elif not is_max_or_full and was_max_or_full:
                print('DEBUG: Window restored to normal from maximized/fullscreen.')
                self.app_state.loaded_previous_geometry = QByteArray()
                print('DEBUG: Cleared loaded_previous_geometry.')
                self._exit_interactive_mode_if_settled(force_redraw=True)
                QTimer.singleShot(60, self.app._ensure_minimum_size_after_restore)

    def handle_close_event(self, event):
        print('DEBUG: handle_close_event called. Saving settings.')
        self.app.thread_pool.waitForDone()
        print('DEBUG: All rendering tasks finished. Proceeding with close.')
        self.app.settings_manager.save_all_settings(self.app_state, self.app)

    def handle_focus_in(self, event):
        pass

    def _handle_interactive_movement_and_lerp(self):
        if self.app_state.showing_single_image_mode != 0:
            return
        magnifier_active = self.app_state.use_magnifier
        split_line_active = not self.app_state.use_magnifier and (self.app_state.original_image1 and self.app_state.original_image2)
        if not magnifier_active and (not split_line_active) and (not self.app_state.is_dragging_any_slider):
            if self.movement_timer.isActive():
                self.movement_timer.stop()
            self._exit_interactive_mode_if_settled(force_redraw=False)
            return
        current_elapsed = self.movement_elapsed_timer.elapsed()
        delta_time_ms = current_elapsed - self.last_update_elapsed
        self.last_update_elapsed = current_elapsed
        delta_time_sec = delta_time_ms / 1000.0
        epsilon = sys.float_info.epsilon
        target_pos_changed_by_input = False
        target_spacing_changed_by_input = False
        target_split_changed_by_input = False
        active_movement_keys = any((key in self.app_state.pressed_keys for key in [Qt.Key.Key_W.value, Qt.Key.Key_A.value, Qt.Key.Key_S.value, Qt.Key.Key_D.value]))
        active_spacing_keys = any((key in self.app_state.pressed_keys for key in [Qt.Key.Key_Q.value, Qt.Key.Key_E.value]))
        if magnifier_active and (active_movement_keys or active_spacing_keys):
            self.app_state.magnifier_is_keyboard_panning = True
            dx_dir = (Qt.Key.Key_D.value in self.app_state.pressed_keys) - (Qt.Key.Key_A.value in self.app_state.pressed_keys)
            dy_dir = (Qt.Key.Key_S.value in self.app_state.pressed_keys) - (Qt.Key.Key_W.value in self.app_state.pressed_keys)
            ds_dir = (Qt.Key.Key_E.value in self.app_state.pressed_keys) - (Qt.Key.Key_Q.value in self.app_state.pressed_keys)
            length_sq = dx_dir * dx_dir + dy_dir * dy_dir
            if length_sq > 1.0 + epsilon:
                inv_length = 1.0 / math.sqrt(length_sq)
                dx_dir *= inv_length
                dy_dir *= inv_length
            speed_multiplier = self.app_state.movement_speed_per_sec
            if dx_dir != 0 or dy_dir != 0:
                relative_speed = AppConstants.BASE_MOVEMENT_SPEED * speed_multiplier
                delta_x = dx_dir * relative_speed * delta_time_sec
                delta_y = dy_dir * relative_speed * delta_time_sec
                if self.app_state.freeze_magnifier:
                    if self.app_state.frozen_magnifier_position_relative:
                        new_x = max(0.0, min(1.0, self.app_state.frozen_magnifier_position_relative.x() + delta_x))
                        new_y = max(0.0, min(1.0, self.app_state.frozen_magnifier_position_relative.y() + delta_y))
                        if not math.isclose(new_x, self.app_state.frozen_magnifier_position_relative.x(), abs_tol=AppConstants.MIN_CHANGE_THRESHOLD) or not math.isclose(new_y, self.app_state.frozen_magnifier_position_relative.y(), abs_tol=AppConstants.MIN_CHANGE_THRESHOLD):
                            self.app_state.frozen_magnifier_position_relative.setX(new_x)
                            self.app_state.frozen_magnifier_position_relative.setY(new_y)
                            target_pos_changed_by_input = True
                else:
                    clamped_dx = max(-AppConstants.MAX_TARGET_DELTA_PER_TICK, min(AppConstants.MAX_TARGET_DELTA_PER_TICK, delta_x))
                    clamped_dy = max(-AppConstants.MAX_TARGET_DELTA_PER_TICK, min(AppConstants.MAX_TARGET_DELTA_PER_TICK, delta_y))
                    new_x = self.app_state.magnifier_offset_relative.x() + clamped_dx
                    new_y = self.app_state.magnifier_offset_relative.y() + clamped_dy
                    if not math.isclose(new_x, self.app_state.magnifier_offset_relative.x(), abs_tol=AppConstants.MIN_CHANGE_THRESHOLD) or not math.isclose(new_y, self.app_state.magnifier_offset_relative.y(), abs_tol=AppConstants.MIN_CHANGE_THRESHOLD):
                        self.app_state.magnifier_offset_relative.setX(new_x)
                        self.app_state.magnifier_offset_relative.setY(new_y)
                        target_pos_changed_by_input = True
            if ds_dir != 0:
                spacing_speed = self.app_state.movement_speed_per_sec
                delta_spacing = ds_dir * spacing_speed * delta_time_sec
                clamped_ds = max(-AppConstants.MAX_TARGET_DELTA_PER_TICK, min(AppConstants.MAX_TARGET_DELTA_PER_TICK, delta_spacing))
                new_spacing = self.app_state.magnifier_spacing_relative + clamped_ds
                new_spacing_clamped = max(0.0, min(0.5, new_spacing))
                if not math.isclose(new_spacing_clamped, self.app_state.magnifier_spacing_relative, abs_tol=AppConstants.MIN_CHANGE_THRESHOLD):
                    self.app_state.magnifier_spacing_relative = new_spacing_clamped
                    target_spacing_changed_by_input = True
        else:
            self.app_state.magnifier_is_keyboard_panning = False
        visual_pos_moved_by_lerp = False
        visual_spacing_moved_by_lerp = False
        visual_split_moved_by_lerp = False
        if magnifier_active and (not self.app_state.freeze_magnifier):
            delta_vx = self.app_state.magnifier_offset_relative.x() - self.app_state.magnifier_offset_relative_visual.x()
            delta_vy = self.app_state.magnifier_offset_relative.y() - self.app_state.magnifier_offset_relative_visual.y()
            if abs(delta_vx) < AppConstants.LERP_STOP_THRESHOLD and abs(delta_vy) < AppConstants.LERP_STOP_THRESHOLD:
                if not math.isclose(self.app_state.magnifier_offset_relative_visual.x(), self.app_state.magnifier_offset_relative.x(), abs_tol=epsilon) or not math.isclose(self.app_state.magnifier_offset_relative_visual.y(), self.app_state.magnifier_offset_relative.y(), abs_tol=epsilon):
                    self.app_state.magnifier_offset_relative_visual.setX(self.app_state.magnifier_offset_relative.x())
                    self.app_state.magnifier_offset_relative_visual.setY(self.app_state.magnifier_offset_relative.y())
                    visual_pos_moved_by_lerp = True
            else:
                new_visual_x = self.app_state.magnifier_offset_relative_visual.x() + delta_vx * AppConstants.SMOOTHING_FACTOR_POS
                new_visual_y = self.app_state.magnifier_offset_relative_visual.y() + delta_vy * AppConstants.SMOOTHING_FACTOR_POS
                self.app_state.magnifier_offset_relative_visual.setX(new_visual_x)
                self.app_state.magnifier_offset_relative_visual.setY(new_visual_y)
                visual_pos_moved_by_lerp = True
            delta_vs = self.app_state.magnifier_spacing_relative - self.app_state.magnifier_spacing_relative_visual
            if abs(delta_vs) < AppConstants.LERP_STOP_THRESHOLD:
                if not math.isclose(self.app_state.magnifier_spacing_relative_visual, self.app_state.magnifier_spacing_relative, abs_tol=epsilon):
                    self.app_state.magnifier_spacing_relative_visual = self.app_state.magnifier_spacing_relative
                    visual_spacing_moved_by_lerp = True
            else:
                new_visual_spacing = self.app_state.magnifier_spacing_relative_visual + delta_vs * AppConstants.SMOOTHING_FACTOR_SPACING
                self.app_state.magnifier_spacing_relative_visual = max(0.0, min(0.5, new_visual_spacing))
                visual_spacing_moved_by_lerp = True
        elif magnifier_active and self.app_state.freeze_magnifier:
            self.app_state.magnifier_offset_relative_visual = QPointF(self.app_state.magnifier_offset_relative)
            self.app_state.magnifier_spacing_relative_visual = self.app_state.magnifier_spacing_relative
            self.app_state.magnifier_is_actively_lerping = False
        else:
            self.app_state.magnifier_is_actively_lerping = False
        if split_line_active:
            delta_split_visual = self.app_state.split_position - self.app_state.split_position_visual
            if abs(delta_split_visual) < AppConstants.LERP_STOP_THRESHOLD:
                if not math.isclose(self.app_state.split_position_visual, self.app_state.split_position, abs_tol=epsilon):
                    self.app_state.split_position_visual = self.app_state.split_position
                    visual_split_moved_by_lerp = True
            else:
                new_visual_split = self.app_state.split_position_visual + delta_split_visual * AppConstants.SMOOTHING_FACTOR_SPLIT
                self.app_state.split_position_visual = max(0.0, min(1.0, new_visual_split))
                visual_split_moved_by_lerp = True
            self.app_state.split_is_actively_lerping = visual_split_moved_by_lerp
        else:
            self.app_state.split_is_actively_lerping = False
        magnifier_visuals_settled = not (visual_pos_moved_by_lerp or visual_spacing_moved_by_lerp)
        split_visual_settled = not visual_split_moved_by_lerp
        is_currently_interactive = self.app_state.is_dragging_split_line or self.app_state.is_dragging_capture_point or self.app_state.magnifier_is_keyboard_panning or self.app_state.is_dragging_any_slider or (magnifier_active and (not self.app_state.freeze_magnifier) and (not magnifier_visuals_settled)) or (split_line_active and (not split_visual_settled))
        if is_currently_interactive:
            if not self.app_state.is_interactive_mode:
                self._enter_interactive_mode()
            needs_redraw = target_pos_changed_by_input or target_spacing_changed_by_input or target_split_changed_by_input or visual_pos_moved_by_lerp or visual_spacing_moved_by_lerp or visual_split_moved_by_lerp
            if needs_redraw and (not self.app_state.resize_in_progress):
                try:
                    self._request_interactive_update()
                except Exception as e:
                    print(f'ERROR: _handle_interactive_movement_and_lerp redraw logic: {e}')
                    traceback.print_exc()
            if not self.movement_timer.isActive():
                print('DEBUG: Starting movement timer for magnifier control/lerping.')
                self.movement_elapsed_timer.start()
                self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
                self.movement_timer.start()
        elif self.app_state.is_interactive_mode:
            print('DEBUG: Visuals settled and no active input. Exiting interactive mode.')
            if self.movement_timer.isActive():
                self.movement_timer.stop()
            self._exit_interactive_mode_if_settled(force_redraw=True)
        elif self.movement_timer.isActive():
            self.movement_timer.stop()
            print('DEBUG: Movement timer stopped as no interactive state.')
        if not (self.app_state.is_dragging_capture_point or self.app_state.magnifier_is_keyboard_panning or self.app_state.is_dragging_split_line or self.app_state.is_dragging_any_slider):
            if magnifier_visuals_settled and magnifier_active and (not self.app_state.freeze_magnifier):
                self.app.settings_manager._save_setting('magnifier_offset_relative', self.app_state.magnifier_offset_relative)
                self.app.settings_manager._save_setting('magnifier_spacing_relative', self.app_state.magnifier_spacing_relative)
            if split_visual_settled and split_line_active:
                self.app.settings_manager._save_setting('split_position', self.app_state.split_position)

    def _enter_interactive_mode(self):
        if not self.app_state.is_interactive_mode:
            print('DEBUG: Entered interactive mode.')
            self.app_state.is_interactive_mode = True
            self.app_state.clear_split_cache()
            self.app_state.clear_magnifier_cache()
            content_rect = self.app.image_label.contentsRect()
            self.app_state.fixed_label_width = content_rect.width()
            self.app_state.fixed_label_height = content_rect.height()
            print(f'DEBUG: Updated app_state.fixed_label_width/height for interactive session: {self.app_state.fixed_label_width}x{self.app_state.fixed_label_height}')
            if hasattr(self.app, 'image_label') and self.app.image_label is not None:
                if self.app.image_label.pixmap() and (not self.app.image_label.pixmap().isNull()):
                    if not self.app.current_displayed_pixmap or self.app.current_displayed_pixmap.cacheKey() != self.app.image_label.pixmap().cacheKey():
                        self.app.current_displayed_pixmap = self.app.image_label.pixmap().copy()
                        print(f'DEBUG: enter_interactive: Updated current_displayed_pixmap from label.')
                if self.app.current_displayed_pixmap and (not self.app.current_displayed_pixmap.isNull()):
                    current_label_pixmap_before_set = self.app.image_label.pixmap()
                    if current_label_pixmap_before_set is None or current_label_pixmap_before_set.isNull() or current_label_pixmap_before_set.cacheKey() != self.app.current_displayed_pixmap.cacheKey():
                        print(f'DEBUG: enter_interactive: Restoring current_displayed_pixmap to label.')
                        self.app.image_label.setPixmap(self.app.current_displayed_pixmap)
            if not self.interactive_update_timer.isActive():
                self.interactive_update_timer.start()
                self.pending_interactive_update = True
            if (self.app_state.use_magnifier or (not self.app_state.use_magnifier and self.app_state.original_image1 and self.app_state.original_image2) or self.app_state.is_dragging_any_slider) and (not self.movement_timer.isActive()):
                print('DEBUG: Starting movement timer on _enter_interactive_mode (interactive mode ON).')
                self.movement_elapsed_timer.start()
                self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
                self.movement_timer.start()

    def _exit_interactive_mode_if_settled(self, force_redraw: bool=False):
        still_interacting_by_user_input = self.app_state.is_dragging_split_line or self.app_state.is_dragging_capture_point or self.app_state.magnifier_is_keyboard_panning or self.app_state.is_dragging_any_slider
        magnifier_visuals_lerping = False
        if self.app_state.use_magnifier and (not self.app_state.freeze_magnifier):
            pos_delta_x = abs(self.app_state.magnifier_offset_relative.x() - self.app_state.magnifier_offset_relative_visual.x())
            pos_delta_y = abs(self.app_state.magnifier_offset_relative.y() - self.app_state.magnifier_offset_relative_visual.y())
            spacing_delta = abs(self.app_state.magnifier_spacing_relative - self.app_state.magnifier_spacing_relative_visual)
            if pos_delta_x >= AppConstants.LERP_STOP_THRESHOLD or pos_delta_y >= AppConstants.LERP_STOP_THRESHOLD or spacing_delta >= AppConstants.LERP_STOP_THRESHOLD:
                magnifier_visuals_lerping = True
        split_visual_lerping = False
        if not self.app_state.use_magnifier:
            split_delta = abs(self.app_state.split_position - self.app_state.split_position_visual)
            if split_delta >= AppConstants.LERP_STOP_THRESHOLD:
                split_visual_lerping = True
        if still_interacting_by_user_input or magnifier_visuals_lerping or split_visual_lerping:
            print('DEBUG: _exit_interactive_mode_if_settled: Still interactive or lerping. NOT exiting interactive mode yet.')
            return
        if self.app_state.is_interactive_mode or force_redraw:
            print(f'DEBUG: _exit_interactive_mode_if_settled: Exiting interactive mode. Force redraw: {force_redraw}')
            self.app_state.is_interactive_mode = False
            self.app_state.magnifier_is_actively_lerping = False
            self.app_state.split_is_actively_lerping = False
            self.app_state.clear_split_cache()
            self.app_state.clear_magnifier_cache()
            print('DEBUG: Caches cleared for final high-quality render.')
            self.interactive_update_timer.stop()
            self.pending_interactive_update = False
            self.app_state.fixed_label_width = None
            self.app_state.fixed_label_height = None
            print('DEBUG: Fixed label sizes reset in app_state.')

            def do_final_render_prep_and_call():
                print('DEBUG: do_final_render_prep_and_call: Applying panel visibility, stabilizing, and updating comparison.')
                if hasattr(self.app, 'image_label') and self.app.image_label is not None:
                    if self.app.image_label.pixmap() and (not self.app.image_label.pixmap().isNull()):
                        if not self.app.current_displayed_pixmap or self.app.current_displayed_pixmap.cacheKey() != self.app.image_label.pixmap().cacheKey():
                            self.app.current_displayed_pixmap = self.app.image_label.pixmap().copy()
                            print(f'DEBUG: final_prep: Updated current_displayed_pixmap from label.')
                    if self.app.current_displayed_pixmap and (not self.app.current_displayed_pixmap.isNull()):
                        current_label_pixmap_before_set = self.app.image_label.pixmap()
                        if current_label_pixmap_before_set is None or current_label_pixmap_before_set.isNull() or current_label_pixmap_before_set.cacheKey() != self.app.current_displayed_pixmap.cacheKey():
                            print(f'DEBUG: final_prep: Restoring current_displayed_pixmap to label.')
                            self.app.image_label.setPixmap(self.app.current_displayed_pixmap)
                try:
                    if hasattr(self.app, '_apply_panel_visibility'):
                        self.app._apply_panel_visibility()
                    else:
                        print('WARNING: self.app has no _apply_panel_visibility method in EventHandler.')
                    if hasattr(self.app, '_stabilize_ui_layout'):
                        self.app._stabilize_ui_layout()
                    else:
                        print('WARNING: self.app has no _stabilize_ui_layout method in EventHandler.')
                    worker_was_queued = False
                    if hasattr(self.app, 'update_comparison_if_needed'):
                        worker_was_queued = self.app.update_comparison_if_needed()
                    else:
                        print('WARNING: self.app has no update_comparison_if_needed method in EventHandler.')
                except Exception as e_prep:
                    print(f'ERROR in do_final_render_prep_and_call preparation: {e_prep}')
                    traceback.print_exc()
                    if hasattr(self.app, 'image_label') and self.app.image_label is not None:
                        if not self.app.image_label.updatesEnabled():
                            self.app.image_label.setUpdatesEnabled(True)
                            self.app.image_label.update()
                            print('DEBUG: do_final_render_prep_and_call: image_label updates re-enabled (on error).')
                finally:
                    pass
            QTimer.singleShot(0, do_final_render_prep_and_call)
        elif self.movement_timer.isActive():
            self.movement_timer.stop()
            print('DEBUG: Movement timer stopped because no longer interactive and no force_redraw.')

    def _is_in_left_area(self, pos: QPoint) -> bool:
        if not hasattr(self.app, 'image_label') or not self.app.image_label.isVisible():
            return True
        try:
            pixmap = self.app.image_label.pixmap()
            content_rect = self.app.image_label.contentsRect()
            label_width = content_rect.width()
            label_height = content_rect.height()
            label_width = max(1, label_width)
            label_height = max(1, label_height)
            if pixmap is None or pixmap.isNull():
                pixmap_x, pixmap_y = (0, 0)
                pixmap_width, pixmap_height = (label_width, label_height)
            else:
                scaled_pixmap_width = pixmap.width()
                scaled_pixmap_height = pixmap.height()
                x_offset = max(0, (label_width - scaled_pixmap_width) // 2)
                y_offset = max(0, (label_height - scaled_pixmap_height) // 2)
                pixmap_x = x_offset
                pixmap_y = y_offset
                pixmap_width = scaled_pixmap_width
                pixmap_height = scaled_pixmap_height
            if pixmap_width <= 0:
                pixmap_width = 1
            if pixmap_height <= 0:
                pixmap_height = 1
            relative_pos_x = pos.x() - content_rect.x() - pixmap_x
            relative_pos_y = pos.y() - content_rect.y() - pixmap_y
            if not self.app_state.is_horizontal:
                center_x_rel_to_pixmap = pixmap_width // 2
                result = relative_pos_x < center_x_rel_to_pixmap
                return result
            else:
                center_y_rel_to_pixmap = pixmap_height // 2
                result = relative_pos_y < center_y_rel_to_pixmap
                return result
        except Exception as e:
            print(f'[DEBUG] Error in _is_in_left_area: {e}')
            traceback.print_exc()
            return True