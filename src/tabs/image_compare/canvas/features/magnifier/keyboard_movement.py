"""Magnifier WASD-Q-E keyboard movement controller.

Owns the QTimer-driven interactive movement cycle for magnifier overlays:
parses pressed WASD/QE keys, damps visual interpolation state, dispatches
viewport actions, syncs the fast overlay preview.

This file used to live in ``events/app_event/interactive_movement.py``; it
moved here because every meaningful line is magnifier-specific (overlay
movement keys, ``overlay.movement_handler`` alias, overlay preview rebuild).
Shared event code (``events/runtime.py``) constructs the controller via the
``keyboard_movement.build_controller`` capability alias and degrades to a
no-op stub if the magnifier feature is absent.
"""

from __future__ import annotations

import logging

import shiboken6 as sip
from PySide6.QtCore import QElapsedTimer, Qt, QTimer

from core.state_management.actions import (
    SetInteractiveInternalSplitVisualAction,
    SetInteractiveModeAction,
    SetInteractiveOffsetVisualAction,
    SetInteractiveSpacingVisualAction,
    SetSplitPositionVisualAction,
)
from domain.types import Point
from events.app_event.common import (
    clear_presenter_render_snapshots,
    emit_update_request,
    get_event_bus,
    get_main_controller,
)
from tabs.image_compare.events.canvas_helpers import (
    get_image_canvas_presenter,
    schedule_image_canvas_update,
)
from events.app_event.interactive_movement_input import (
    apply_offset_input,
    apply_spacing_input,
    collect_movement_keys,
    compute_speed_factor,
    resolve_movement_directions,
)
from events.app_event.interactive_movement_math import damp, damp_vector, is_close
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

logger = logging.getLogger("ImproveImgSLI")


def _get_movement_handler(store):
    cmd = get_canvas_feature_command_by_alias("overlay.movement_handler")
    if cmd is None:
        return None
    return cmd(store)


class InteractiveMovementController:
    OVERLAY_MOVEMENT_KEYS = {
        Qt.Key.Key_A,
        Qt.Key.Key_D,
        Qt.Key.Key_W,
        Qt.Key.Key_S,
        Qt.Key.Key_Q,
        Qt.Key.Key_E,
    }

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
        self._last_debug_signature = None
        self._spacing_hold_time = 0.0

    @property
    def presenter(self):
        return self._presenter_provider()

    def _dispatch_viewport_action(self, action) -> bool:
        dispatcher = getattr(self.store, "_dispatcher", None)
        if dispatcher is None:
            return False
        dispatcher.dispatch(action, scope="viewport")
        return True

    def _set_interactive_mode(self, enabled: bool) -> None:
        self._dispatch_viewport_action(SetInteractiveModeAction(enabled))

    def _set_visual_state(
        self,
        *,
        offset: Point | None = None,
        spacing: float | None = None,
        internal_split: float | None = None,
        split_visual: float | None = None,
    ) -> None:
        if offset is not None:
            self._dispatch_viewport_action(SetInteractiveOffsetVisualAction(offset))
        if spacing is not None:
            self._dispatch_viewport_action(SetInteractiveSpacingVisualAction(spacing))
        if internal_split is not None:
            self._dispatch_viewport_action(
                SetInteractiveInternalSplitVisualAction(internal_split)
            )
        if split_visual is not None:
            self._dispatch_viewport_action(SetSplitPositionVisualAction(split_visual))

    def start(self) -> None:
        viewport_ctrl = getattr(
            get_main_controller(self.presenter), "viewport_plugin", None
        )
        if viewport_ctrl is not None and hasattr(
            viewport_ctrl, "begin_user_interaction"
        ):
            viewport_ctrl.begin_user_interaction()

        handler = _get_movement_handler(self.store)
        if handler is not None:
            offset = handler.get_offset()
            spacing = handler.get_spacing()
            internal_split = handler.get_internal_split()
            if offset is not None:
                self._set_visual_state(
                    offset=offset,
                    spacing=spacing,
                    internal_split=internal_split,
                )

        if not self.store.viewport.view_state.optimize_interactive_movement:
            self._set_interactive_mode(False)
            self.store.invalidate_render_cache()
            self.store.emit_viewport_change("interaction")
            emit_update_request(self.presenter)
        elif not self.store.viewport.interaction_state.is_interactive_mode:
            self._set_interactive_mode(True)
            self.store.invalidate_render_cache()
            self.store.emit_viewport_change("interaction")

        if not self.movement_timer.isActive():
            self.movement_elapsed_timer.start()
            self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
            self.movement_timer.start()
            self._last_input_dirs = (0, 0, 0)

    def stop(self) -> None:
        viewport_ctrl = getattr(
            get_main_controller(self.presenter), "viewport_plugin", None
        )
        if viewport_ctrl is not None and hasattr(viewport_ctrl, "end_user_interaction"):
            viewport_ctrl.end_user_interaction()

        if self.store.viewport.interaction_state.is_interactive_mode:
            self._set_interactive_mode(False)
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
            self.store.viewport.view_state.optimize_interactive_movement
            and not self.store.viewport.interaction_state.is_interactive_mode
        ):
            self._set_interactive_mode(True)

        handler = _get_movement_handler(self.store)
        state_changed = self._apply_keyboard_input(delta_time_sec, handler)
        if handler is not None:
            handler.emit_combined_state(event_bus=get_event_bus(self.presenter))

        if self._should_finish_cycle(delta_time_sec, handler):
            self._finish_interactive_cycle(handler)
            return

        self._set_interactive_mode(True)
        if (
            state_changed
            or self.store.viewport.view_state.optimize_interactive_movement
        ):
            emit_update_request(self.presenter)
            schedule_image_canvas_update(self.presenter)

    def _stop_for_single_image_mode(self) -> None:
        if not self.movement_timer.isActive():
            return
        self.movement_timer.stop()
        self._set_interactive_mode(False)
        self.store.emit_viewport_change("interaction")
        emit_update_request(self.presenter)

    def _apply_keyboard_input(self, delta_time_sec: float, handler) -> bool:
        keys = collect_movement_keys(
            self.store.viewport.interaction_state.pressed_keys,
            self.OVERLAY_MOVEMENT_KEYS,
        )
        if not keys or not self.store.viewport.view_state.overlay_enabled:
            self._log_input_resolution(keys, 0, 0, 0, note="no_keys_or_disabled")
            self._last_input_dirs = (0, 0, 0)
            return False

        if handler is None:
            self._last_input_dirs = (0, 0, 0)
            return False

        directions = resolve_movement_directions(
            self.store.viewport.interaction_state,
            keys,
        )
        dx_dir, dy_dir, ds_dir = directions.as_tuple()
        if directions.is_zero():
            self._log_input_resolution(keys, dx_dir, dy_dir, ds_dir, note="zero_dirs")
            self._last_input_dirs = (0, 0, 0)
            return False

        self._log_input_resolution(keys, dx_dir, dy_dir, ds_dir)

        speed_factor = compute_speed_factor(self.store.viewport.view_state)

        previous_dirs = self._last_input_dirs
        self._last_input_dirs = (dx_dir, dy_dir, ds_dir)

        current_offset = handler.get_offset()
        if current_offset is None:
            return False

        new_offset, offset_changed = apply_offset_input(
            current_offset,
            directions,
            speed_factor,
            delta_time_sec,
        )

        if offset_changed:
            handler.set_offset(new_offset)
            self._snap_visual_offset_on_direction_change(
                previous_dirs, self._last_input_dirs, handler
            )
            self.store.emit_viewport_change("interaction")

        after_emit = handler.get_offset()
        if after_emit is not None and after_emit != new_offset:
            handler.set_offset(after_emit)

        spacing_changed = False
        if ds_dir != 0:
            self._spacing_hold_time += delta_time_sec
            spacing_changed = self._apply_spacing_input(
                speed_factor, delta_time_sec, ds_dir, handler
            )
        else:
            self._spacing_hold_time = 0.0
        return offset_changed or spacing_changed

    def _apply_spacing_input(
        self, speed_factor: float, delta_time_sec: float, ds_dir: int, handler
    ) -> bool:
        if not handler.has_both_sides():
            return False

        current_spacing = handler.get_spacing()
        if current_spacing is None:
            return False

        min_sp, max_sp = handler.get_spacing_limits()
        clamped_spacing, changed = apply_spacing_input(
            current_spacing,
            ds_dir,
            speed_factor,
            delta_time_sec,
            min_spacing=min_sp,
            max_spacing=max_sp,
            hold_time=self._spacing_hold_time,
        )
        handler.set_spacing(clamped_spacing)
        if changed:
            self.store.emit_viewport_change("interaction")
        return changed

    def _should_finish_cycle(self, delta_time_sec: float, handler) -> bool:
        interaction_state = getattr(self.store.viewport, "interaction_state", None)
        pressed_keys_set = (
            getattr(interaction_state, "pressed_keys", set())
            if interaction_state is not None
            else set()
        )
        movement_keys_pressed = any(
            key in self.OVERLAY_MOVEMENT_KEYS for key in pressed_keys_set
        )
        is_user_inputting = (
            self.store.viewport.interaction_state.is_dragging_split_line
            or self.store.viewport.interaction_state.is_dragging_overlay_handle
            or self.store.viewport.interaction_state.is_dragging_overlay_split
            or self.store.viewport.interaction_state.is_dragging_any_slider
            or movement_keys_pressed
        )

        if handler is None:
            return not is_user_inputting

        optimize_movement = self.store.viewport.view_state.optimize_interactive_movement
        target_offset = handler.get_offset()
        target_spacing = handler.get_spacing()
        target_internal_split = handler.get_internal_split()
        if target_offset is None:
            return not is_user_inputting

        if optimize_movement:
            new_offset_visual = damp_vector(
                self.store.viewport.interaction_state.interactive_offset_relative_visual,
                target_offset,
                20.0,
                delta_time_sec,
            )
            new_spacing_visual = damp(
                self.store.viewport.interaction_state.interactive_spacing_relative_visual,
                target_spacing or 0.0,
                25.0,
                delta_time_sec,
            )
            if self.store.viewport.interaction_state.is_dragging_overlay_split:
                new_internal_split_visual = target_internal_split or 0.5
            else:
                new_internal_split_visual = damp(
                    self.store.viewport.interaction_state.interactive_internal_split_visual,
                    target_internal_split or 0.5,
                    25.0,
                    delta_time_sec,
                )
            if self.store.viewport.interaction_state.is_dragging_split_line:
                new_split_visual = self.store.viewport.view_state.split_position
            else:
                new_split_visual = damp(
                    self.store.viewport.view_state.split_position_visual,
                    self.store.viewport.view_state.split_position,
                    25.0,
                    delta_time_sec,
                )
        else:
            new_offset_visual = target_offset
            new_spacing_visual = target_spacing or 0.0
            new_internal_split_visual = target_internal_split or 0.5
            new_split_visual = self.store.viewport.view_state.split_position

        self._set_visual_state(
            offset=new_offset_visual,
            spacing=new_spacing_visual,
            internal_split=new_internal_split_visual,
            split_visual=new_split_visual,
        )
        self._sync_fast_overlay_preview()

        stop_threshold = 0.0005
        is_converged = (
            is_close(new_offset_visual, target_offset, stop_threshold)
            and abs(new_spacing_visual - (target_spacing or 0.0)) < stop_threshold
            and abs(new_internal_split_visual - (target_internal_split or 0.5))
            < stop_threshold
            and abs(new_split_visual - self.store.viewport.view_state.split_position)
            < stop_threshold
        )
        return not is_user_inputting and (not optimize_movement or is_converged)

    def _finish_interactive_cycle(self, handler=None) -> None:
        self.movement_timer.stop()
        if handler is not None:
            offset = handler.get_offset()
            spacing = handler.get_spacing()
            internal_split = handler.get_internal_split()
        else:
            offset = None
            spacing = None
            internal_split = None
        self._set_visual_state(
            offset=offset if offset is not None else Point(0.0, 0.0),
            spacing=spacing if spacing is not None else 0.0,
            internal_split=internal_split if internal_split is not None else 0.5,
            split_visual=self.store.viewport.view_state.split_position,
        )
        self._set_interactive_mode(False)

        self.store.invalidate_render_cache()
        clear_presenter_render_snapshots(self.presenter)
        self.store.emit_viewport_change("interaction")
        emit_update_request(self.presenter)

    def _sync_fast_overlay_preview(self) -> None:
        image_canvas_presenter = get_image_canvas_presenter(self.presenter)
        if image_canvas_presenter is None:
            return
        image_label = getattr(
            getattr(image_canvas_presenter, "ui", None), "image_label", None
        )
        if image_label is None or not sip.isValid(image_label):
            return
        if (
            hasattr(image_canvas_presenter, "view")
            and image_canvas_presenter.view.is_canvas_widget()
        ):
            image_canvas_presenter.overlay.rebuild_overlay()
        elif hasattr(image_canvas_presenter, "overlay"):
            image_canvas_presenter.overlay.rebuild_overlay()

    def _snap_visual_offset_on_direction_change(
        self, previous_dirs, current_dirs, handler
    ) -> None:
        prev_dx, prev_dy, _ = previous_dirs
        cur_dx, cur_dy, _ = current_dirs
        viewport = self.store.viewport
        visual = viewport.interaction_state.interactive_offset_relative_visual
        target = handler.get_offset()
        if target is None:
            return
        snapped_x = target.x if prev_dx and cur_dx and prev_dx != cur_dx else visual.x
        snapped_y = target.y if prev_dy and cur_dy and prev_dy != cur_dy else visual.y
        if snapped_x != visual.x or snapped_y != visual.y:
            self._set_visual_state(offset=Point(snapped_x, snapped_y))

    def _log_input_resolution(
        self,
        keys,
        dx_dir: int,
        dy_dir: int,
        ds_dir: int,
        *,
        note: str | None = None,
    ) -> None:
        interaction = self.store.viewport.interaction_state
        signature = (
            tuple(sorted(int(key) for key in keys)),
            (
                None
                if interaction.last_horizontal_movement_key is None
                else int(interaction.last_horizontal_movement_key)
            ),
            (
                None
                if interaction.last_vertical_movement_key is None
                else int(interaction.last_vertical_movement_key)
            ),
            (
                None
                if interaction.last_spacing_movement_key is None
                else int(interaction.last_spacing_movement_key)
            ),
            int(dx_dir),
            int(dy_dir),
            int(ds_dir),
            note or "",
        )
        if signature == self._last_debug_signature:
            return
        self._last_debug_signature = signature


def build_controller(store, *, presenter_provider, parent=None):
    return InteractiveMovementController(
        store, presenter_provider=presenter_provider, parent=parent
    )
