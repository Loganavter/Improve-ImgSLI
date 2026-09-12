import PIL.Image

from tabs.image_compare.canvas.registry import registry
from tabs.image_compare.presenters.image_canvas.background_parts.render_flow import (
    schedule_update as schedule_update_impl,
)
from tabs.image_compare.presenters.image_canvas.background_parts.render_flow import (
    should_use_dirty_rects_optimization,
)
from tabs.image_compare.presenters.image_canvas.background_parts.render_flow import (
    update_comparison_if_needed as update_comparison_if_needed_impl,
)
from tabs.image_compare.presenters.image_canvas.lifecycle import (
    debug_log_gate,
    get_current_label_dimensions,
    initialize_canvas_presenter,
    invalidate_render_state,
    start_interactive_movement,
    update_minimum_window_size,
)
from tabs.image_compare.presenters.image_canvas.signatures import (
    get_background_signature,
    get_divider_color_tuple,
    get_magnifier_signature,
    get_render_params_signature,
)
from tabs.image_compare.presenters.image_canvas.view import (
    display_single_image_on_label,
    is_canvas_widget,
    set_image_layers,
)


def _get_overlay_runtime_command(capability_id: str):
    return registry().get_feature_command_by_alias(capability_id)


class CanvasLifecycleCoordinator:
    def __init__(self, presenter):
        self.presenter = presenter

    def initialize(self):
        initialize_canvas_presenter(self.presenter)

    def debug_log_gate(self):
        return debug_log_gate()

    def connect_event_handler_signals(self, event_handler):
        self.presenter.image_label_handler.keyboard_state_service = (
            event_handler.keyboard_state
        )
        event_handler.mouse_press_event_on_image_label_signal.connect(
            self.presenter.image_label_handler.handle_mouse_press
        )
        event_handler.mouse_move_event_on_image_label_signal.connect(
            self.presenter.image_label_handler.handle_mouse_move
        )
        event_handler.mouse_release_event_on_image_label_signal.connect(
            self.presenter.image_label_handler.handle_mouse_release
        )
        event_handler.canvas_keyboard_press_event_signal.connect(
            self.presenter.image_label_handler.handle_key_press
        )
        event_handler.canvas_keyboard_release_event_signal.connect(
            self.presenter.image_label_handler.handle_key_release
        )
        event_handler.mouse_wheel_event_on_image_label_signal.connect(
            self.presenter.image_label_handler.handle_wheel_scroll
        )
        event_handler.drag_enter_event_signal.connect(
            self.presenter.window_handler.handle_drag_enter
        )
        event_handler.drag_move_event_signal.connect(
            self.presenter.window_handler.handle_drag_move
        )
        event_handler.drag_leave_event_signal.connect(
            self.presenter.window_handler.handle_drag_leave
        )
        event_handler.drop_event_signal.connect(
            self.presenter.window_handler.handle_drop
        )
        event_handler.resize_event_signal.connect(
            self.presenter.window_handler.handle_resize
        )
        event_handler.close_event_signal.connect(
            self.presenter.window_handler.handle_close
        )
        self._connect_canvas_input_routing(event_handler)

    def _connect_canvas_input_routing(self, event_handler):
        image_label = getattr(self.presenter.widget, "image_label", None)
        if image_label is None:
            return
        image_label.set_store(self.presenter.store)
        if hasattr(image_label, "set_session_controller"):
            sessions = getattr(self.presenter.main_controller, "sessions", None)
            if sessions is not None:
                image_label.set_session_controller(sessions)
        image_label.mousePressed.connect(
            event_handler.mouse_press_event_on_image_label_signal.emit
        )
        image_label.mouseMoved.connect(
            event_handler.mouse_move_event_on_image_label_signal.emit
        )
        image_label.mouseReleased.connect(
            event_handler.mouse_release_event_on_image_label_signal.emit
        )
        image_label.wheelScrolled.connect(
            event_handler.mouse_wheel_event_on_image_label_signal.emit
        )
        image_label.zoomChanged.connect(self.presenter.widget.update_zoom_indicator)
        image_label.zoomChanged.connect(self._on_canvas_zoom_changed)
        btn_zoom_reset = getattr(self.presenter.widget, "btn_zoom_reset", None)
        if btn_zoom_reset is not None:
            btn_zoom_reset.clicked.connect(lambda: image_label.reset_view())

    def _on_canvas_zoom_changed(self, _zoom):
        toolbar = self._resolve_toolbar_presenter(self.presenter)
        if toolbar is not None and hasattr(toolbar, "update_toolbar_states"):
            toolbar.update_toolbar_states()

    @staticmethod
    def _resolve_toolbar_presenter(presenter):
        controller = getattr(presenter, "main_controller", None)
        shell = getattr(controller, "window_shell", None) if controller is not None else None
        if shell is None:
            shell = getattr(getattr(presenter, "main_window_app", None), "presenter", None)
        if shell is not None and hasattr(shell, "get_feature"):
            return shell.get_feature("toolbar")
        return None

    def get_current_label_dimensions(self) -> tuple[int, int]:
        return get_current_label_dimensions(self.presenter)

    def update_minimum_window_size(self):
        return update_minimum_window_size(self.presenter)

    def invalidate_render_state(self, clear_overlay_state: bool = False):
        return invalidate_render_state(self.presenter)

    def start_interactive_movement(self):
        return start_interactive_movement(self.presenter)


class CanvasViewCoordinator:
    def __init__(self, presenter):
        self.presenter = presenter

    def is_canvas_widget(self):
        return is_canvas_widget(self.presenter)

    def set_image_layers(
        self, background=None, overlay=None, overlay_pos=None, coords_snapshot=None
    ):
        return set_image_layers(
            self.presenter, background, overlay, overlay_pos, coords_snapshot
        )

    def display_single_image_on_label(self, pil_image: PIL.Image.Image | None):
        return display_single_image_on_label(self.presenter, pil_image)

    def get_divider_color_tuple(self, vp):
        return get_divider_color_tuple(vp)


class CanvasBackgroundCoordinator:
    def __init__(self, presenter):
        self.presenter = presenter

    def schedule_update(self):
        return schedule_update_impl(self.presenter)

    def update_comparison_if_needed(self) -> bool:
        return update_comparison_if_needed_impl(self.presenter)

    def get_render_params_signature(self, s1, s2):
        return get_render_params_signature(self.presenter, s1, s2)

    def get_background_signature(self, s1, s2):
        return get_background_signature(self.presenter, s1, s2)

    def should_use_dirty_rects_optimization(
        self, render_params_dict: dict, label_dims: tuple | None = None
    ) -> bool:
        return should_use_dirty_rects_optimization(
            self.presenter, render_params_dict, label_dims
        )


class CanvasOverlayCoordinator:
    def __init__(self, presenter):
        self.presenter = presenter

    def get_signature(self):
        return get_magnifier_signature(self.presenter)

    def rebuild_overlay(self):
        command = _get_overlay_runtime_command("overlay.rebuild")
        return command(self.presenter) if command is not None else None

    def render_layer(self, sig) -> bool:
        command = _get_overlay_runtime_command("overlay.render_layer")
        return bool(command(self.presenter, sig)) if command is not None else False

    def stop_interactive_movement(self):
        command = _get_overlay_runtime_command("overlay.stop_interactive_movement")
        if command is None:
            return None
        return command(self.presenter, self.presenter.lifecycle.debug_log_gate())

    def update_capture_area_display(self):
        command = _get_overlay_runtime_command("overlay.update_capture_area_display")
        return command(self.presenter) if command is not None else None
