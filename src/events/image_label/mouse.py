from __future__ import annotations

from PyQt6.QtCore import Qt

from events.canvas_input.session_service import (
    CAPTURE_DRAG_OWNER,
    INTERNAL_SPLIT_DRAG_OWNER,
    KEYBOARD_MOVE_OWNER,
    SPLIT_DRAG_OWNER,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

class ImageLabelMouseHandler:
    def __init__(self, handler):
        self.handler = handler

    def handle_mouse_press(self, event) -> None:
        viewport = self.handler.store.viewport
        local_pos = self.handler.geometry.event_position_in_label(event, clamp=True)
        preview_buttons = event.buttons() & (
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
        )
        both_preview_buttons_pressed = preview_buttons == (
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
        )
        shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        _q = get_canvas_feature_command_by_alias("overlay.active_state")
        active_overlay = (_q(self.handler.store) if _q is not None else None) or {}
        _qc = get_canvas_feature_command_by_alias("overlay.active_combined")
        is_combined = bool(_qc(self.handler.store)) if _qc is not None else False

        self.handler.preview.log_preview_debug(
            "mouse_press",
            button=event.button().name,
            buttons=int(event.buttons().value),
            space=viewport.interaction_state.space_bar_pressed,
            shift=shift_pressed,
            mag_preview=self.handler.preview.is_active,
            single_mode=viewport.view_state.showing_single_image_mode,
            combined=is_combined,
            left=bool(active_overlay.get("visible_left", False)),
            right=bool(active_overlay.get("visible_right", False)),
        )
        has_left = bool(active_overlay.get("visible_left", False))
        has_right = bool(active_overlay.get("visible_right", False))
        is_enabled = self.handler.store.viewport.view_state.overlay_enabled

        if viewport.interaction_state.space_bar_pressed and both_preview_buttons_pressed:
            self.handler.preview.log_preview_debug("mouse_press_ignored_both_buttons")
            event.accept()
            return

        if self.handler.preview.is_active and viewport.interaction_state.space_bar_pressed and shift_pressed:
            if event.button() == Qt.MouseButton.RightButton:
                self.handler.preview.switch_side("right")
                event.accept()
                return
            if event.button() == Qt.MouseButton.LeftButton:
                self.handler.preview.switch_side("left")
                event.accept()
                return
            self.handler.preview.log_preview_debug("mouse_press_ignored_active_shift_preview")
            event.accept()
            return

        if (
            viewport.interaction_state.space_bar_pressed
            and shift_pressed
            and is_enabled
            and is_combined
            and has_left
            and has_right
            and viewport.view_state.showing_single_image_mode == 0
            and not viewport.interaction_state.resize_in_progress
            and self.handler.geometry.is_point_in_overlay(local_pos)
        ):
            if event.button() == Qt.MouseButton.LeftButton:
                self.handler.preview.start_side_preview("left")
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton:
                self.handler.preview.start_side_preview("right")
                event.accept()
                return

        if viewport.interaction_state.space_bar_pressed:
            if (
                event.button() == Qt.MouseButton.LeftButton
                and self.handler.main_controller is not None
                and self.handler.main_controller.sessions is not None
            ):
                self.handler.preview.log_preview_debug("single_preview_started", side="left")
                self.handler.main_controller.sessions.activate_single_image_mode(1)
            elif (
                event.button() == Qt.MouseButton.RightButton
                and self.handler.main_controller is not None
                and self.handler.main_controller.sessions is not None
            ):
                self.handler.preview.log_preview_debug(
                    "single_preview_started", side="right"
                )
                self.handler.main_controller.sessions.activate_single_image_mode(2)
            event.accept()
            return

        if (
            viewport.view_state.showing_single_image_mode != 0
            or not viewport.session_data.image_state.image1
            or viewport.interaction_state.resize_in_progress
        ):
            return

        if is_enabled:
            self.handler.geometry.get_overlay_at_position(local_pos)

        if event.button() == Qt.MouseButton.LeftButton:
            if is_enabled:
                command = get_canvas_feature_command_by_alias(
                    "overlay.begin_capture_drag",
                )
                if command is not None:
                    command(self.handler)
                self.handler.input_session.activate(CAPTURE_DRAG_OWNER)
                self.handler.geometry.update_state_from_mouse_position(
                    local_pos, respect_overlay=False
                )
            else:
                command = get_canvas_feature_command_by_alias(
                    "splitter.begin_drag",
                )
                if command is not None:
                    command(self.handler)
                self.handler.input_session.activate(SPLIT_DRAG_OWNER)
                self.handler.geometry.update_state_from_mouse_position(local_pos)
            event.accept()
        elif (
            event.button() == Qt.MouseButton.RightButton
            and is_enabled
            and is_combined
            and self.handler.geometry.is_point_in_overlay(local_pos)
        ):
            command = get_canvas_feature_command_by_alias(
                "overlay.begin_internal_split_drag",
            )
            if command is not None:
                command(self.handler)
            self.handler.input_session.activate(INTERNAL_SPLIT_DRAG_OWNER)
            self.handler.geometry.update_overlay_internal_split(local_pos)
            event.accept()
        elif (
            event.button() == Qt.MouseButton.RightButton
            and is_enabled
            and self.handler.input_session.has_owner(KEYBOARD_MOVE_OWNER)
        ):
            event.accept()

    def handle_mouse_move(self, event) -> None:
        viewport = self.handler.store.viewport
        local_pos = self.handler.geometry.event_position_in_label(event, clamp=True)
        if viewport.view_state.showing_single_image_mode != 0 or viewport.interaction_state.resize_in_progress:
            return

        if self.handler._mouse_move_timer.elapsed() < 8:
            return
        self.handler._mouse_move_timer.restart()

        if event.buttons() & Qt.MouseButton.LeftButton and (
            viewport.interaction_state.is_dragging_split_line or viewport.interaction_state.is_dragging_overlay_handle
        ):
            self.handler.geometry.update_state_from_mouse_position(
                local_pos,
                respect_overlay=not viewport.interaction_state.is_dragging_overlay_handle,
            )
            event.accept()

        if (
            event.buttons() & Qt.MouseButton.RightButton
            and viewport.interaction_state.is_dragging_overlay_split
        ):
            self.handler.geometry.update_overlay_internal_split(local_pos)
            event.accept()

    def handle_mouse_release(self, event) -> None:
        viewport = self.handler.store.viewport
        if self.handler.preview.is_active:
            if (
                viewport.interaction_state.space_bar_pressed
                and bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            ):
                self.handler.preview.log_preview_debug(
                    "mouse_release_keeps_shift_preview",
                    button=event.button().name,
                )
                event.accept()
                return
            self.handler.preview.log_preview_debug(
                "mouse_release_restores_shift_preview",
                button=event.button().name,
            )
            self.handler.preview.restore()
            event.accept()
            return
        if viewport.interaction_state.space_bar_pressed:
            self.handler.preview.log_preview_debug(
                "mouse_release_while_space_preview",
                button=event.button().name,
            )
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            had_capture = viewport.interaction_state.is_dragging_overlay_handle
            had_split = viewport.interaction_state.is_dragging_split_line
            if had_capture:
                command = get_canvas_feature_command_by_alias(
                    "overlay.end_capture_drag",
                )
                if command is not None:
                    command(self.handler)
            if had_split:
                command = get_canvas_feature_command_by_alias(
                    "splitter.end_drag",
                )
                if command is not None:
                    command(self.handler)
            elif had_capture:
                self.handler.store.emit_viewport_change("interaction")
            if had_capture:
                self.handler.input_session.deactivate(CAPTURE_DRAG_OWNER)
            if had_split:
                self.handler.input_session.deactivate(SPLIT_DRAG_OWNER)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            had_internal_split = viewport.interaction_state.is_dragging_overlay_split
            if had_internal_split:
                command = get_canvas_feature_command_by_alias(
                    "overlay.end_internal_split_drag",
                )
                if command is not None:
                    command(self.handler)
            if had_internal_split:
                self.handler.input_session.deactivate(INTERNAL_SPLIT_DRAG_OWNER)
            event.accept()

    def handle_wheel_scroll(self, event) -> None:
        viewport = self.handler.store.viewport
        delta = event.angleDelta().y()
        if abs(delta) < 1:
            return

        cursor_pos = event.position()
        raw_rel_x, raw_rel_y = self.handler.geometry.screen_to_image_rel(cursor_pos)
        if raw_rel_x is None:
            label_size = (
                self.handler.parent().get_current_label_dimensions()
                if self.handler.parent()
                else (1, 1)
            )
            raw_rel_x = cursor_pos.x() / float(label_size[0])
            raw_rel_y = cursor_pos.y() / float(label_size[1])

        sync_scroll = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if sync_scroll:
            if self.handler.main_controller and self.handler.main_controller.sessions:
                self.handler.main_controller.sessions.on_combobox_changed(1, -1, delta)
                self.handler.main_controller.sessions.on_combobox_changed(2, -1, delta)
                event.accept()
            return

        if viewport.view_state.showing_single_image_mode != 0:
            image_number = viewport.view_state.showing_single_image_mode
        else:
            rel_pos = raw_rel_x if not viewport.view_state.is_horizontal else raw_rel_y
            image_number = 1 if rel_pos < viewport.view_state.split_position_visual else 2

        if self.handler.main_controller and self.handler.main_controller.sessions:
            self.handler.main_controller.sessions.on_combobox_changed(
                image_number, -1, delta
            )
            event.accept()
