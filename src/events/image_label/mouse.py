from __future__ import annotations

from PyQt6.QtCore import Qt

from ui.canvas_infra.scene.gesture_resolver import (
    GesturePressContext,
    iter_active,
    resolve_press,
)

class ImageLabelMouseHandler:
    """Mouse routing for the image-label widget.

    All canvas-gesture decisions live in feature-declared
    ``CanvasFeatureGestureBinding`` entries; this handler only resolves the
    winning binding and invokes its callables. The few app-level workflows
    that remain here (active-preview side-switch on release, single-image
    mode activation on space+click) are not canvas features and have no
    natural home in any feature package.
    """

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

        self.handler.preview.log_preview_debug(
            "mouse_press",
            button=event.button().name,
            buttons=int(event.buttons().value),
            space=viewport.interaction_state.space_bar_pressed,
            shift=shift_pressed,
            mag_preview=self.handler.preview.is_active,
            single_mode=viewport.view_state.showing_single_image_mode,
        )

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
            viewport.view_state.showing_single_image_mode != 0
            or not viewport.session_data.image_state.image1
            or viewport.interaction_state.resize_in_progress
        ):
            return

        ctx = GesturePressContext(
            store=self.handler.store,
            handler=self.handler,
            local_pos=local_pos,
            button=event.button().value,
            modifiers=int(event.modifiers().value),
        )
        binding = resolve_press(ctx)
        if binding is not None:
            if binding.begin is not None:
                binding.begin(self.handler, local_pos)
            if binding.owner is not None:
                self.handler.input_session.activate(binding.owner)
            event.accept()
            return

        if viewport.interaction_state.space_bar_pressed:
            sessions = self.handler.main_controller and self.handler.main_controller.sessions
            if sessions is not None:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.handler.preview.log_preview_debug("single_preview_started", side="left")
                    sessions.activate_single_image_mode(1)
                elif event.button() == Qt.MouseButton.RightButton:
                    self.handler.preview.log_preview_debug("single_preview_started", side="right")
                    sessions.activate_single_image_mode(2)
            event.accept()

    def handle_mouse_move(self, event) -> None:
        viewport = self.handler.store.viewport
        local_pos = self.handler.geometry.event_position_in_label(event, clamp=True)
        if viewport.view_state.showing_single_image_mode != 0 or viewport.interaction_state.resize_in_progress:
            return

        if self.handler._mouse_move_timer.elapsed() < 8:
            return
        self.handler._mouse_move_timer.restart()

        active = iter_active(self.handler.store)
        if not active:
            return

        buttons = event.buttons()
        consumed = False
        for binding in active:
            if not (buttons & Qt.MouseButton(binding.button)):
                continue
            if binding.update is not None:
                binding.update(self.handler, local_pos)
                consumed = True
        if consumed:
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

        released_button = event.button().value
        ended_any = False
        for binding in iter_active(self.handler.store):
            if binding.button != released_button:
                continue
            if binding.end is not None:
                binding.end(self.handler)
            if binding.owner is not None:
                self.handler.input_session.deactivate(binding.owner)
            ended_any = True
        if ended_any:
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
