

import logging
import math
import traceback

from PyQt6.QtCore import QElapsedTimer, QEvent, QObject, QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit

from core.constants import AppConstants
from core.events import (
    ViewportUpdateMagnifierCombinedStateEvent,
    ExportPasteImageFromClipboardEvent,
    ViewportSetMagnifierInternalSplitEvent,
)
from events.drag_drop_handler import DragAndDropService

logger = logging.getLogger("ImproveImgSLI")

class EventHandler(QObject):
    drag_enter_event_signal = pyqtSignal(QDragEnterEvent)
    drag_move_event_signal = pyqtSignal(QDragMoveEvent)
    drag_leave_event_signal = pyqtSignal(QEvent)
    drop_event_signal = pyqtSignal(QDropEvent)
    resize_event_signal = pyqtSignal(QEvent)
    close_event_signal = pyqtSignal(QEvent)
    mouse_press_event_signal = pyqtSignal(QMouseEvent)
    keyboard_press_event_signal = pyqtSignal(QKeyEvent)
    keyboard_release_event_signal = pyqtSignal(QKeyEvent)
    mouse_press_event_on_image_label_signal = pyqtSignal(QMouseEvent)
    mouse_move_event_on_image_label_signal = pyqtSignal(QMouseEvent)
    mouse_release_event_on_image_label_signal = pyqtSignal(QMouseEvent)
    mouse_wheel_event_on_image_label_signal = pyqtSignal(QWheelEvent)

    def __init__(self, store, presenter_ref):
        super().__init__()
        self.store = store
        self.presenter = presenter_ref

        self.movement_timer = QTimer(self)
        self.movement_timer.setInterval(0)
        self.movement_timer.timeout.connect(self._handle_interactive_movement_and_lerp)
        self.movement_elapsed_timer = QElapsedTimer()
        self.last_update_elapsed = 0
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._finish_resize)

        self.keyboard_press_event_signal.connect(self.handle_key_press)
        self.keyboard_release_event_signal.connect(self.handle_key_release)

    @property
    def event_bus(self):
        if self.presenter is not None and self.presenter.main_controller is not None:
            return self.presenter.main_controller.event_bus
        return None

    def eventFilter(self, watched_obj, event: QEvent) -> bool:
        event_type = event.type()

        dnd_service = DragAndDropService.get_instance()
        if dnd_service.is_dragging():
            if event_type == QEvent.Type.MouseMove:
                dnd_service.update_drag_position(event)
                return True
            if event_type == QEvent.Type.MouseButtonRelease:
                dnd_service.finish_drag(event)
                return True
            if event_type == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                dnd_service.cancel_drag()
                return True
            if event_type in [QEvent.Type.MouseButtonPress, QEvent.Type.Enter, QEvent.Type.Leave]:
                return True

        if event_type == QEvent.Type.MouseButtonPress:
            self.mouse_press_event_signal.emit(event)

        if event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if self._should_route_key_event_globally(event, watched_obj):
                if event_type == QEvent.Type.KeyPress:
                    self.keyboard_press_event_signal.emit(event)
                else:
                    self.keyboard_release_event_signal.emit(event)
                return True

        main_window = self.presenter.main_window_app if self.presenter else None
        if watched_obj is main_window:
            if event_type == QEvent.Type.DragEnter:
                self.drag_enter_event_signal.emit(event)
                return True
            if event_type == QEvent.Type.DragMove:
                self.drag_move_event_signal.emit(event)
                return True
            if event_type == QEvent.Type.DragLeave:
                self.drag_leave_event_signal.emit(event)
                return True
            if event_type == QEvent.Type.Drop:
                self.drop_event_signal.emit(event)
                return True
            if event_type == QEvent.Type.Resize:
                self.resize_timer.stop()
                self.resize_timer.start(200)
                self.resize_event_signal.emit(event)
            if event_type == QEvent.Type.Close:
                dnd_service.cancel_drag()
                self.close_event_signal.emit(event)

        return super().eventFilter(watched_obj, event)

    def start_interactive_movement(self):
        if not self.store.viewport.is_interactive_mode:
            self.store.viewport.is_interactive_mode = True
            self.store.invalidate_render_cache()
            self.store.emit_state_change()
        if not self.movement_timer.isActive():
            self.movement_elapsed_timer.start()
            self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
            self.movement_timer.start()

    def stop_interactive_movement(self):
        if self.store.viewport.is_interactive_mode:
            self.store.viewport.is_interactive_mode = False
            self.store.emit_state_change()
            if self.presenter and hasattr(self.presenter, 'main_controller'):
                self.presenter.main_controller.update_requested.emit()

    def _handle_interactive_movement_and_lerp(self):
        if self.store.viewport.showing_single_image_mode != 0:
            if self.movement_timer.isActive():
                self.movement_timer.stop()
                self.store.viewport.is_interactive_mode = False
                self.store.emit_state_change()
                if self.presenter and hasattr(self.presenter, 'main_controller'):
                    self.presenter.main_controller.update_requested.emit()
            return

        delta_time_ms = (
            self.movement_elapsed_timer.elapsed() - self.last_update_elapsed
        )
        if delta_time_ms <= 0:
            return

        self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
        delta_time_sec = delta_time_ms / 1000.0

        if not self.store.viewport.is_interactive_mode:
            self.store.viewport.is_interactive_mode = True

        if self.store.viewport.pressed_keys:

            if self.store.viewport.use_magnifier:
                keys = self.store.viewport.pressed_keys
                dx_dir = (Qt.Key.Key_D in keys) - (Qt.Key.Key_A in keys)
                dy_dir = (Qt.Key.Key_S in keys) - (Qt.Key.Key_W in keys)
                ds_dir = (Qt.Key.Key_E in keys) - (Qt.Key.Key_Q in keys)

                if dx_dir != 0 or dy_dir != 0 or ds_dir != 0:
                    speed_factor = (
                        self.store.viewport.movement_speed_per_sec
                        * AppConstants.BASE_MOVEMENT_SPEED
                    )

                    new_offset = self.store.viewport.magnifier_offset_relative

                    if dx_dir != 0 or dy_dir != 0:
                        length = math.sqrt(dx_dir**2 + dy_dir**2)
                        if length > 1.0:
                            dx_dir /= length
                            dy_dir /= length

                        delta_x = dx_dir * speed_factor * delta_time_sec
                        delta_y = dy_dir * speed_factor * delta_time_sec

                        new_offset = self.store.viewport.magnifier_offset_relative + QPointF(delta_x, delta_y)

                    self.store.viewport.magnifier_offset_relative = new_offset

                    self.store.emit_state_change()

                    after_emit = self.store.viewport.magnifier_offset_relative
                    if after_emit != new_offset:
                        logger.warning(f"[MAGNIFIER OFFSET] Value changed after emit_state_change: set={new_offset}, after_emit={after_emit}")

                    if self.presenter and hasattr(self.presenter, 'main_controller'):
                        self.presenter.main_controller.update_requested.emit()

                    if self.presenter and hasattr(self.presenter, 'image_canvas_presenter'):
                        self.presenter.image_canvas_presenter.schedule_update()

                    if ds_dir != 0:
                        delta_spacing = ds_dir * speed_factor * delta_time_sec

                        new_spacing = self.store.viewport.magnifier_spacing_relative + delta_spacing
                        clamped_spacing = max(
                            AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE,
                            min(AppConstants.MAX_MAGNIFIER_SPACING_RELATIVE, new_spacing)
                        )

                        self.store.viewport.magnifier_spacing_relative = clamped_spacing

                        self.store.emit_state_change()

                        if self.presenter and hasattr(self.presenter, 'main_controller'):
                            self.presenter.main_controller.update_requested.emit()

                        if self.presenter and hasattr(self.presenter, 'image_canvas_presenter'):
                            self.presenter.image_canvas_presenter.schedule_update()

        if self.store.viewport.use_magnifier:

            if self.event_bus:
                self.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())

        pressed_keys_set = getattr(self.store.viewport.view_state, 'pressed_keys', set()) if hasattr(self.store.viewport, 'view_state') else self.store.viewport.pressed_keys

        is_still_interacting = (
            self.store.viewport.is_dragging_split_line
            or self.store.viewport.is_dragging_capture_point
            or self.store.viewport.is_dragging_split_in_magnifier
            or self.store.viewport.is_dragging_any_slider
            or bool(pressed_keys_set)
        )

        if is_still_interacting or self.store.viewport.is_interactive_mode:
            new_offset_visual = self._lerp_vector(
                self.store.viewport.magnifier_offset_relative_visual,
                self.store.viewport.magnifier_offset_relative,
                AppConstants.SMOOTHING_FACTOR_POS,
            )
            new_spacing_visual = self._lerp_scalar(
                self.store.viewport.magnifier_spacing_relative_visual,
                self.store.viewport.magnifier_spacing_relative,
                AppConstants.SMOOTHING_FACTOR_SPACING,
            )
            new_split_visual = self._lerp_scalar(
                self.store.viewport.split_position_visual,
                self.store.viewport.split_position,
                AppConstants.SMOOTHING_FACTOR_SPLIT,
            )

            self.store.viewport.magnifier_offset_relative_visual = new_offset_visual
            self.store.viewport.magnifier_spacing_relative_visual = new_spacing_visual
            self.store.viewport.split_position_visual = new_split_visual

        is_still_lerping = not (
            self._is_close(self.store.viewport.magnifier_offset_relative_visual, self.store.viewport.magnifier_offset_relative) and
            math.isclose(self.store.viewport.magnifier_spacing_relative_visual, self.store.viewport.magnifier_spacing_relative, abs_tol=0.001) and
            math.isclose(self.store.viewport.split_position_visual, self.store.viewport.split_position, abs_tol=0.001)
        )

        if not is_still_interacting and not is_still_lerping:
            self.movement_timer.stop()

            self.store.viewport.magnifier_offset_relative_visual = self.store.viewport.magnifier_offset_relative
            self.store.viewport.magnifier_spacing_relative_visual = self.store.viewport.magnifier_spacing_relative
            self.store.viewport.split_position_visual = self.store.viewport.split_position

            self.store.emit_state_change()
            self.store.viewport.is_interactive_mode = False

            self.store.invalidate_render_cache()

            if self.presenter and hasattr(self.presenter, '_last_store_snapshot'):
                delattr(self.presenter, '_last_store_snapshot')
            if self.presenter and hasattr(self.presenter, '_last_render_params_dict'):
                delattr(self.presenter, '_last_render_params_dict')
            self.store.emit_state_change()

            if self.presenter and hasattr(self.presenter, 'main_controller'):
                self.presenter.main_controller.update_requested.emit()

        else:

            if self.presenter and hasattr(self.presenter, 'main_controller'):
                self.presenter.main_controller.update_requested.emit()

    def _lerp_scalar(self, current, target, factor): return current + (target - current) * factor
    def _lerp_vector(self, current, target, factor): return QPointF(self._lerp_scalar(current.x(), target.x(), factor), self._lerp_scalar(current.y(), target.y(), factor))
    def _is_close(self, p1, p2): return math.isclose(p1.x(), p2.x(), abs_tol=AppConstants.LERP_STOP_THRESHOLD) and math.isclose(p1.y(), p2.y(), abs_tol=AppConstants.LERP_STOP_THRESHOLD)
    def _finish_resize(self):
        self.presenter._finish_resize_delay()

    def _close_all_popups_unconditionally(self):
        stack_trace = ''.join(traceback.format_stack()[-5:-1])
        logger.debug(f"[EventHandler] _close_all_popups_unconditionally вызван\n"
                    f"  Stack trace:\n{stack_trace}")
        if self.presenter is None:
            return

        ui_manager = self.presenter.ui_manager
        if ui_manager is not None and ui_manager.unified_flyout is not None and ui_manager.unified_flyout.isVisible():
            logger.debug(f"[EventHandler] _close_all_popups_unconditionally: закрываю unified_flyout")
            ui_manager.unified_flyout.start_closing_animation()
            if hasattr(self.presenter, 'ui') and self.presenter.ui is not None:
                if hasattr(self.presenter.ui, 'combo_image1'):
                    self.presenter.ui.combo_image1.setFlyoutOpen(False)
                if hasattr(self.presenter.ui, 'combo_image2'):
                    self.presenter.ui.combo_image2.setFlyoutOpen(False)

        if hasattr(self.presenter, 'font_settings_flyout') and self.presenter.font_settings_flyout is not None:
            if self.presenter.font_settings_flyout.isVisible():
                self.presenter.font_settings_flyout.hide()

    def _should_route_key_event_globally(self, event: QKeyEvent, watched_obj: QObject) -> bool:

        magnifier_keys = {
            Qt.Key.Key_Q,
            Qt.Key.Key_E,
            Qt.Key.Key_W,
            Qt.Key.Key_A,
            Qt.Key.Key_S,
            Qt.Key.Key_D,
        }

        space_key = Qt.Key.Key_Space

        if self.presenter is not None and hasattr(self.presenter, 'ui') and self.presenter.ui is not None:
            image_label = getattr(self.presenter.ui, "image_label", None)
            if watched_obj is image_label:
                return False

        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):

            if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                return False

            if event.key() == Qt.Key.Key_S and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                return False

            return False

        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return True

        if key == Qt.Key.Key_S and modifiers == Qt.KeyboardModifier.ControlModifier:
            return True
        if key == Qt.Key.Key_S and modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            return True
        if key == space_key:
            return True

        if key in magnifier_keys:
            return True
        return False

    def handle_key_press(self, event: QKeyEvent):
        key_code = event.key()
        modifiers = event.modifiers()

        if key_code == Qt.Key.Key_V and modifiers & Qt.KeyboardModifier.ControlModifier:
            if self.event_bus:
                self.event_bus.emit(ExportPasteImageFromClipboardEvent())
            event.accept()
            return

        magnifier_keys = {
            Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S,
            Qt.Key.Key_D, Qt.Key.Key_Q, Qt.Key.Key_E
        }

        is_magnifier_key = key_code in magnifier_keys

        self.store.viewport.pressed_keys.add(key_code)
        self.store.emit_state_change()

        if key_code == Qt.Key.Key_Space:
            if event.isAutoRepeat():
                return
            self.store.viewport.space_bar_pressed = True
            self.store.emit_state_change()

        if is_magnifier_key and self.store.viewport.use_magnifier:

            self.start_interactive_movement()
        elif not is_magnifier_key:

            self.start_interactive_movement()

    def handle_key_release(self, event: QKeyEvent):
        key_code = event.key()
        self.store.viewport.pressed_keys.discard(key_code)
        self.store.emit_state_change()

        if key_code == Qt.Key.Key_Space:
            if event.isAutoRepeat():
                return
            self.store.viewport.space_bar_pressed = False
            self.store.emit_state_change()

            if self.store.viewport.showing_single_image_mode != 0:
                if self.presenter and hasattr(self.presenter, 'main_controller') and self.presenter.main_controller:
                    if self.presenter.main_controller and self.presenter.main_controller.session_ctrl:
                        self.presenter.main_controller.session_ctrl.deactivate_single_image_mode()

    def _is_point_in_magnifier(self, pos: QPointF) -> bool:
        vp = self.store.viewport
        if not vp.magnifier_screen_size:
            return False

        mag_center = vp.magnifier_screen_center
        mag_size = vp.magnifier_screen_size

        dx = pos.x() - mag_center.x()
        dy = pos.y() - mag_center.y()

        return (dx * dx + dy * dy) <= (mag_size / 2.0)**2

    def _update_magnifier_internal_split(self, cursor_pos: QPointF):
        vp = self.store.viewport
        if not vp.magnifier_screen_size:
            return

        mag_center = vp.magnifier_screen_center
        mag_size = vp.magnifier_screen_size

        clamped_val = 0.5
        if not vp.magnifier_is_horizontal:
            left_edge = mag_center.x() - mag_size / 2.0
            rel_x = (cursor_pos.x() - left_edge) / mag_size if mag_size > 0 else 0.5
            clamped_val = max(0.0, min(1.0, rel_x))
        else:
            top_edge = mag_center.y() - mag_size / 2.0
            rel_y = (cursor_pos.y() - top_edge) / mag_size if mag_size > 0 else 0.5
            clamped_val = max(0.0, min(1.0, rel_y))

        if vp.magnifier_internal_split != clamped_val:
            vp.magnifier_internal_split = clamped_val

            self.store.emit_state_change()

            if self.presenter and hasattr(self.presenter, 'main_controller') and self.presenter.main_controller:
                self.presenter.main_controller.update_requested.emit()
