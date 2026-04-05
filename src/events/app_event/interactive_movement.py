from __future__ import annotations

import math
from PyQt6 import sip
from PyQt6.QtCore import QElapsedTimer, QTimer, Qt

from core.constants import AppConstants
from core.events import ViewportUpdateMagnifierCombinedStateEvent
from domain.types import Point
from events.app_event.common import (
    clear_presenter_render_snapshots,
    emit_update_request,
    get_event_bus,
    get_image_canvas_presenter,
    get_main_controller,
    schedule_image_canvas_update,
)

class InteractiveMovementController:
    def __init__(self, store, presenter_provider, parent=None):
        self.store = store
        self._presenter_provider = presenter_provider

        self.movement_timer = QTimer(parent)

        self.movement_timer.setInterval(8)
        self.movement_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.movement_timer.timeout.connect(self.handle_timer_tick)
        self.movement_elapsed_timer = QElapsedTimer()
        self.last_update_elapsed = 0
        self._last_input_dirs = (0, 0, 0)

    @property
    def presenter(self):
        return self._presenter_provider()

    def start(self) -> None:
        viewport_ctrl = getattr(get_main_controller(self.presenter), "viewport_plugin", None)
        if viewport_ctrl is not None and hasattr(viewport_ctrl, "begin_user_interaction"):
            viewport_ctrl.begin_user_interaction()

        if not self.store.viewport.view_state.optimize_magnifier_movement:
            self.store.viewport.interaction_state.is_interactive_mode = False
            self.store.invalidate_render_cache()
            self.store.emit_viewport_change("interaction")
            emit_update_request(self.presenter)
        elif not self.store.viewport.interaction_state.is_interactive_mode:
            self.store.viewport.interaction_state.is_interactive_mode = True
            self.store.invalidate_render_cache()
            self.store.emit_viewport_change("interaction")

        if not self.movement_timer.isActive():
            self.movement_elapsed_timer.start()
            self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
            self.movement_timer.start()
            self._last_input_dirs = (0, 0, 0)

    def stop(self) -> None:
        viewport_ctrl = getattr(get_main_controller(self.presenter), "viewport_plugin", None)
        if viewport_ctrl is not None and hasattr(viewport_ctrl, "end_user_interaction"):
            viewport_ctrl.end_user_interaction()

        if self.store.viewport.interaction_state.is_interactive_mode:
            self.store.viewport.interaction_state.is_interactive_mode = False
            self.store.emit_viewport_change("interaction")
            emit_update_request(self.presenter)
        if self.movement_timer.isActive():
            self.movement_timer.stop()

    def handle_timer_tick(self) -> None:
        if self.store.viewport.view_state.showing_single_image_mode != 0:
            self._stop_for_single_image_mode()
            return

        delta_time_ms = self.movement_elapsed_timer.elapsed() - self.last_update_elapsed
        if delta_time_ms <= 0:
            return

        self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
        delta_time_sec = min(delta_time_ms / 1000.0, 0.016)

        if (
            self.store.viewport.view_state.optimize_magnifier_movement
            and not self.store.viewport.interaction_state.is_interactive_mode
        ):
            self.store.viewport.interaction_state.is_interactive_mode = True

        state_changed = self._apply_keyboard_input(delta_time_sec)
        self._emit_magnifier_combined_state()

        if self._should_finish_cycle(delta_time_sec):
            self._finish_interactive_cycle()
            return

        self.store.viewport.interaction_state.is_interactive_mode = True
        if state_changed or self.store.viewport.view_state.optimize_magnifier_movement:
            emit_update_request(self.presenter)
            schedule_image_canvas_update(self.presenter)

    def _stop_for_single_image_mode(self) -> None:
        if not self.movement_timer.isActive():
            return
        self.movement_timer.stop()
        self.store.viewport.interaction_state.is_interactive_mode = False
        self.store.emit_viewport_change("interaction")
        emit_update_request(self.presenter)

    def _apply_keyboard_input(self, delta_time_sec: float) -> bool:
        if not self.store.viewport.interaction_state.pressed_keys or not self.store.viewport.view_state.use_magnifier:
            self._last_input_dirs = (0, 0, 0)
            return False

        keys = self.store.viewport.interaction_state.pressed_keys
        dx_dir = self._resolve_axis_direction(
            keys,
            self.store.viewport.interaction_state.last_horizontal_movement_key,
            negative_key=Qt.Key.Key_A,
            positive_key=Qt.Key.Key_D,
        )
        dy_dir = self._resolve_axis_direction(
            keys,
            self.store.viewport.interaction_state.last_vertical_movement_key,
            negative_key=Qt.Key.Key_W,
            positive_key=Qt.Key.Key_S,
        )
        ds_dir = self._resolve_axis_direction(
            keys,
            self.store.viewport.interaction_state.last_spacing_movement_key,
            negative_key=Qt.Key.Key_Q,
            positive_key=Qt.Key.Key_E,
        )

        if dx_dir == 0 and dy_dir == 0 and ds_dir == 0:
            self._last_input_dirs = (0, 0, 0)
            return False

        speed_factor = (
            self.store.viewport.view_state.movement_speed_per_sec * AppConstants.BASE_MOVEMENT_SPEED
        )

        previous_dirs = self._last_input_dirs
        self._last_input_dirs = (dx_dir, dy_dir, ds_dir)
        new_offset = self.store.viewport.view_state.magnifier_offset_relative
        offset_changed = False
        if dx_dir != 0 or dy_dir != 0:
            length = math.sqrt(dx_dir**2 + dy_dir**2)
            if length > 1.0:
                dx_dir /= length
                dy_dir /= length

            old_offset = self.store.viewport.view_state.magnifier_offset_relative
            delta_x = dx_dir * speed_factor * delta_time_sec
            delta_y = dy_dir * speed_factor * delta_time_sec
            new_offset = Point(old_offset.x + delta_x, old_offset.y + delta_y)
            offset_changed = (
                not math.isclose(new_offset.x, old_offset.x, abs_tol=1e-9)
                or not math.isclose(new_offset.y, old_offset.y, abs_tol=1e-9)
            )

        if offset_changed:
            self.store.viewport.view_state.magnifier_offset_relative = new_offset
            self._snap_visual_offset_on_direction_change(previous_dirs, self._last_input_dirs)
            self.store.emit_viewport_change("interaction")

        after_emit = self.store.viewport.view_state.magnifier_offset_relative
        if after_emit != new_offset:
            self.store.viewport.view_state.magnifier_offset_relative = after_emit

        spacing_changed = False
        if ds_dir != 0:
            spacing_changed = self._apply_spacing_input(speed_factor, delta_time_sec, ds_dir)
        return offset_changed or spacing_changed

    def _apply_spacing_input(
        self, speed_factor: float, delta_time_sec: float, ds_dir: int
    ) -> bool:
        viewport = self.store.viewport
        if not (viewport.view_state.magnifier_visible_left and viewport.view_state.magnifier_visible_right):
            return False

        delta_spacing = ds_dir * speed_factor * delta_time_sec * 0.35
        old_spacing = viewport.view_state.magnifier_spacing_relative
        new_spacing = viewport.view_state.magnifier_spacing_relative + delta_spacing
        viewport.view_state.magnifier_spacing_relative = max(
            AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE,
            min(AppConstants.MAX_MAGNIFIER_SPACING_RELATIVE, new_spacing),
        )
        changed = not math.isclose(
            viewport.view_state.magnifier_spacing_relative,
            old_spacing,
            abs_tol=1e-9,
        )
        if changed:
            self.store.emit_viewport_change("interaction")
        return changed

    def _emit_magnifier_combined_state(self) -> None:
        if not self.store.viewport.view_state.use_magnifier:
            return
        event_bus = get_event_bus(self.presenter)
        if event_bus is not None:
            event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())

    def _should_finish_cycle(self, delta_time_sec: float) -> bool:
        interaction_state = getattr(self.store.viewport, "interaction_state", None)
        pressed_keys_set = (
            getattr(interaction_state, "pressed_keys", set())
            if interaction_state is not None
            else set()
        )
        is_user_inputting = (
            self.store.viewport.interaction_state.is_dragging_split_line
            or self.store.viewport.interaction_state.is_dragging_capture_point
            or self.store.viewport.interaction_state.is_dragging_split_in_magnifier
            or self.store.viewport.interaction_state.is_dragging_any_slider
            or bool(pressed_keys_set)
        )

        optimize_movement = self.store.viewport.view_state.optimize_magnifier_movement
        target_offset = self.store.viewport.view_state.magnifier_offset_relative
        if optimize_movement:
            new_offset_visual = self._damp_vector(
                self.store.viewport.view_state.magnifier_offset_relative_visual,
                target_offset,
                20.0,
                delta_time_sec,
            )
            new_spacing_visual = self._damp(
                self.store.viewport.view_state.magnifier_spacing_relative_visual,
                self.store.viewport.view_state.magnifier_spacing_relative,
                25.0,
                delta_time_sec,
            )
            if self.store.viewport.interaction_state.is_dragging_split_line:
                new_split_visual = self.store.viewport.view_state.split_position
            else:
                new_split_visual = self._damp(
                    self.store.viewport.view_state.split_position_visual,
                    self.store.viewport.view_state.split_position,
                    25.0,
                    delta_time_sec,
                )
        else:
            new_offset_visual = target_offset
            new_spacing_visual = self.store.viewport.view_state.magnifier_spacing_relative
            new_split_visual = self.store.viewport.view_state.split_position

        self.store.viewport.view_state.magnifier_offset_relative_visual = new_offset_visual
        self.store.viewport.view_state.magnifier_spacing_relative_visual = new_spacing_visual
        self.store.viewport.view_state.split_position_visual = new_split_visual
        self._sync_fast_magnifier_preview()

        stop_threshold = 0.0005
        is_converged = (
            self._is_close(new_offset_visual, target_offset, stop_threshold)
            and abs(new_spacing_visual - self.store.viewport.view_state.magnifier_spacing_relative)
            < stop_threshold
            and abs(new_split_visual - self.store.viewport.view_state.split_position)
            < stop_threshold
        )
        return not is_user_inputting and (not optimize_movement or is_converged)

    def _finish_interactive_cycle(self) -> None:
        self.movement_timer.stop()
        self.store.viewport.view_state.magnifier_offset_relative_visual = (
            self.store.viewport.view_state.magnifier_offset_relative
        )
        self.store.viewport.view_state.magnifier_spacing_relative_visual = (
            self.store.viewport.view_state.magnifier_spacing_relative
        )
        self.store.viewport.view_state.split_position_visual = self.store.viewport.view_state.split_position
        self.store.viewport.interaction_state.is_interactive_mode = False

        self.store.invalidate_render_cache()
        clear_presenter_render_snapshots(self.presenter)
        self.store.emit_viewport_change("interaction")
        emit_update_request(self.presenter)

    def _sync_fast_magnifier_preview(self) -> None:
        image_canvas_presenter = get_image_canvas_presenter(self.presenter)
        if image_canvas_presenter is None:
            return
        image_label = getattr(getattr(image_canvas_presenter, "ui", None), "image_label", None)
        if image_label is None or sip.isdeleted(image_label):
            return
        if hasattr(image_canvas_presenter, "view") and image_canvas_presenter.view.is_gl_canvas():
            if image_canvas_presenter.view.supports_legacy_gl_magnifier():
                image_canvas_presenter.magnifier.render_gl_fast()
            else:
                image_canvas_presenter.magnifier.render_layer(
                    image_canvas_presenter.magnifier.get_signature()
                )
        elif hasattr(image_canvas_presenter, "view"):
            image_canvas_presenter.view.sync_widget_overlay_coords()

    def _snap_visual_offset_on_direction_change(self, previous_dirs, current_dirs) -> None:
        prev_dx, prev_dy, _ = previous_dirs
        cur_dx, cur_dy, _ = current_dirs
        viewport = self.store.viewport
        visual = viewport.view_state.magnifier_offset_relative_visual
        target = viewport.view_state.magnifier_offset_relative
        snapped_x = target.x if prev_dx and cur_dx and prev_dx != cur_dx else visual.x
        snapped_y = target.y if prev_dy and cur_dy and prev_dy != cur_dy else visual.y
        if snapped_x != visual.x or snapped_y != visual.y:
            viewport.view_state.magnifier_offset_relative_visual = Point(snapped_x, snapped_y)

    @staticmethod
    def _resolve_axis_direction(keys, last_key, *, negative_key: int, positive_key: int) -> int:
        negative_down = negative_key in keys
        positive_down = positive_key in keys
        if negative_down and positive_down:
            if last_key == negative_key:
                return -1
            if last_key == positive_key:
                return 1
            return 0
        if positive_down:
            return 1
        if negative_down:
            return -1
        return 0

    def _damp(self, current, target, smoothing, dt):
        return target + (current - target) * math.exp(-smoothing * dt)

    def _damp_vector(self, current: Point, target: Point, smoothing, dt) -> Point:
        return Point(
            self._damp(current.x, target.x, smoothing, dt),
            self._damp(current.y, target.y, smoothing, dt),
        )

    def _is_close(self, p1: Point, p2: Point, tol=None):
        if tol is None:
            tol = AppConstants.LERP_STOP_THRESHOLD
        return math.isclose(p1.x, p2.x, abs_tol=tol) and math.isclose(
            p1.y, p2.y, abs_tol=tol
        )
