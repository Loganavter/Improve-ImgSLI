import logging
import math

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
from events.drag_drop_handler import DragAndDropService

logger = logging.getLogger("ImproveImgSLI")
from resources import translations as translations_mod

tr = getattr(translations_mod, "tr", lambda text, lang="en", *args, **kwargs: text)

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

    def __init__(self, app_instance, app_state, presenter_ref):
        super().__init__(app_instance)
        self.app = app_instance
        self.app_state = app_state
        self.presenter = presenter_ref
        self.movement_timer = QTimer(self)
        self.movement_timer.setInterval(0)
        self.movement_timer.timeout.connect(self._handle_interactive_movement_and_lerp)
        self.movement_elapsed_timer = QElapsedTimer()
        self.last_update_elapsed = 0
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._finish_resize)
        if hasattr(self.app, "ui") and hasattr(self.app.ui, "image_label"):
            image_label = self.app.ui.image_label
            image_label.mousePressed.connect(self.mouse_press_event_on_image_label_signal.emit)
            image_label.mouseMoved.connect(self.mouse_move_event_on_image_label_signal.emit)
            image_label.mouseReleased.connect(self.mouse_release_event_on_image_label_signal.emit)
            image_label.keyPressed.connect(self.keyboard_press_event_signal.emit)
            image_label.keyReleased.connect(self.keyboard_release_event_signal.emit)
            image_label.wheelScrolled.connect(self.mouse_wheel_event_on_image_label_signal.emit)

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

        if watched_obj is self.app:
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
        if not self.app_state.is_interactive_mode:
            self.app_state.is_interactive_mode = True
            self.app_state.clear_interactive_caches()
        if not self.movement_timer.isActive():
            self.movement_elapsed_timer.start()
            self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
            self.movement_timer.start()

    def stop_interactive_movement(self):
        if self.app_state.is_interactive_mode:
            self.app_state.is_interactive_mode = False
            self.presenter.main_window_app.schedule_update()

    def _handle_interactive_movement_and_lerp(self):
        if self.app_state.showing_single_image_mode != 0:
            if self.movement_timer.isActive():
                self.movement_timer.stop()
                self.app_state.is_interactive_mode = False
                self.presenter.main_window_app.schedule_update()
                return

        delta_time_ms = (
            self.movement_elapsed_timer.elapsed() - self.last_update_elapsed
        )
        if delta_time_ms <= 0:
            return

        self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
        delta_time_sec = delta_time_ms / 1000.0

        if self.app_state.use_magnifier and self.app_state.pressed_keys:

            if not self.app_state.freeze_magnifier:
                dx_dir = (Qt.Key.Key_D.value in self.app_state.pressed_keys) - (
                    Qt.Key.Key_A.value in self.app_state.pressed_keys
                )
                dy_dir = (Qt.Key.Key_S.value in self.app_state.pressed_keys) - (
                    Qt.Key.Key_W.value in self.app_state.pressed_keys
                )
            else:

                dx_dir = (Qt.Key.Key_D.value in self.app_state.pressed_keys) - (
                    Qt.Key.Key_A.value in self.app_state.pressed_keys
                )
                dy_dir = (Qt.Key.Key_S.value in self.app_state.pressed_keys) - (
                    Qt.Key.Key_W.value in self.app_state.pressed_keys
                )

            ds_dir = (Qt.Key.Key_E.value in self.app_state.pressed_keys) - (
                Qt.Key.Key_Q.value in self.app_state.pressed_keys
            )

            speed_factor = (
                self.app_state.movement_speed_per_sec
                * AppConstants.BASE_MOVEMENT_SPEED
            )

            if dx_dir != 0 or dy_dir != 0:
                length = math.sqrt(dx_dir**2 + dy_dir**2)
                if length > 1.0:
                    dx_dir /= length
                    dy_dir /= length

                delta_x = dx_dir * speed_factor * delta_time_sec
                delta_y = dy_dir * speed_factor * delta_time_sec

                new_offset = self.app_state.magnifier_offset_relative + QPointF(
                    delta_x, delta_y
                )
                self.app_state.magnifier_offset_relative = new_offset

            if ds_dir != 0:
                delta_spacing = ds_dir * speed_factor * delta_time_sec
                new_spacing = (
                    self.app_state.magnifier_spacing_relative + delta_spacing
                )
                self.app_state.magnifier_spacing_relative = max(
                    AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE, min(AppConstants.MAX_MAGNIFIER_SPACING_RELATIVE, new_spacing)
                )

        self.app_state.magnifier_offset_relative_visual = self._lerp_vector(
            self.app_state.magnifier_offset_relative_visual,
            self.app_state.magnifier_offset_relative,
            AppConstants.SMOOTHING_FACTOR_POS,
        )
        self.app_state.magnifier_spacing_relative_visual = self._lerp_scalar(
            self.app_state.magnifier_spacing_relative_visual,
            self.app_state.magnifier_spacing_relative,
            AppConstants.SMOOTHING_FACTOR_SPACING,
        )
        self.app_state.split_position_visual = self._lerp_scalar(
            self.app_state.split_position_visual,
            self.app_state.split_position,
            AppConstants.SMOOTHING_FACTOR_SPLIT,
        )

        self.presenter.main_window_app.schedule_update()

        is_still_interacting = (
            self.app_state.is_dragging_split_line
            or self.app_state.is_dragging_capture_point
            or self.app_state.is_dragging_split_in_magnifier
            or self.app_state.is_dragging_any_slider
            or bool(self.app_state.pressed_keys)
        )

        is_still_lerping_magnifier = False
        if not self.app_state.freeze_magnifier:
            is_still_lerping_magnifier = not self._is_close(
                self.app_state.magnifier_offset_relative_visual,
                self.app_state.magnifier_offset_relative,
            ) or not math.isclose(
                self.app_state.magnifier_spacing_relative_visual,
                self.app_state.magnifier_spacing_relative,
                abs_tol=AppConstants.LERP_STOP_THRESHOLD,
            )

        is_still_lerping_split = not math.isclose(
            self.app_state.split_position_visual,
            self.app_state.split_position,
            abs_tol=AppConstants.LERP_STOP_THRESHOLD,
        )

        if (
            not is_still_interacting
            and not is_still_lerping_magnifier
            and not is_still_lerping_split
        ):
            self.movement_timer.stop()
            self.app_state.is_interactive_mode = False
            self.presenter.main_window_app.schedule_update()

    def _lerp_scalar(self, current, target, factor): return current + (target - current) * factor
    def _lerp_vector(self, current, target, factor): return QPointF(self._lerp_scalar(current.x(), target.x(), factor), self._lerp_scalar(current.y(), target.y(), factor))
    def _is_close(self, p1, p2): return math.isclose(p1.x(), p2.x(), abs_tol=AppConstants.LERP_STOP_THRESHOLD) and math.isclose(p1.y(), p2.y(), abs_tol=AppConstants.LERP_STOP_THRESHOLD)
    def _finish_resize(self):
        self.presenter._finish_resize_delay()

    def _close_all_popups_unconditionally(self):
        try:
            ui_manager = self.presenter.ui_manager
            if ui_manager and ui_manager.unified_flyout and ui_manager.unified_flyout.isVisible():
                ui_manager.unified_flyout.start_closing_animation()
                try:
                    self.presenter.ui.combo_image1.setFlyoutOpen(False)
                    self.presenter.ui.combo_image2.setFlyoutOpen(False)
                except Exception:
                    pass

            try:
                if hasattr(self.presenter, 'font_settings_flyout') and self.presenter.font_settings_flyout.isVisible():
                    self.presenter.font_settings_flyout.hide()
            except Exception:
                pass
        except Exception:
            pass

    def _should_route_key_event_globally(self, event: QKeyEvent, watched_obj: QObject) -> bool:
        magnifier_keys = {
            Qt.Key.Key_W,
            Qt.Key.Key_A,
            Qt.Key.Key_S,
            Qt.Key.Key_D,
            Qt.Key.Key_Q,
            Qt.Key.Key_E,
        }
        space_key = Qt.Key.Key_Space

        try:
            if hasattr(self.app, "ui") and watched_obj is getattr(self.app.ui, "image_label", None):
                return False
        except Exception:
            pass

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
        if key in magnifier_keys and self.app_state.use_magnifier:
            return True
        return False
