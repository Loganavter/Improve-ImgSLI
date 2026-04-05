import PIL.Image

from ui.presenters.image_canvas.background import (
    create_preview_cache_async,
    ensure_images_scaled,
    ensure_images_unified,
    finish_resize_delay,
    on_display_scaling_ready,
    on_preview_cache_ready,
    render_background,
    schedule_update as schedule_update_impl,
    should_use_dirty_rects_optimization,
    start_scaling_worker,
    update_comparison_if_needed as update_comparison_if_needed_impl,
)
from ui.presenters.image_canvas.lifecycle import (
    debug_log_gate,
    get_current_label_dimensions,
    initialize_canvas_presenter,
    invalidate_render_state,
    start_interactive_movement,
    update_minimum_window_size,
)
from ui.presenters.image_canvas.magnifier import (
    magnifier_worker_task,
    on_capture_patch_ready,
    on_magnifier_layer_ready,
    on_magnifier_patch_ready,
    on_magnifier_worker_error,
    render_capture_area_only_optimized,
    render_magnifier_diff_fallback,
    render_magnifier_gl_fast,
    render_magnifier_layer,
    start_magnifier_only_worker,
    stop_interactive_movement as stop_interactive_movement_impl,
    sync_widget_overlay_coords,
    update_capture_area_display as update_capture_area_display_impl,
    update_widget_capture_area_geometry,
)
from ui.presenters.image_canvas.results import (
    handle_background_result,
    handle_legacy_result,
    handle_magnifier_result,
    on_generic_worker_error,
    on_worker_error,
    on_worker_finished,
)
from ui.presenters.image_canvas.signatures import (
    get_background_signature,
    get_divider_color_tuple,
    get_magnifier_signature,
    get_render_params_signature,
)
from ui.presenters.image_canvas.view import (
    display_single_image_on_label,
    is_gl_canvas,
    prepare_gl_background_layers,
    set_image_layers,
    supports_legacy_gl_magnifier,
)

class CanvasLifecycleCoordinator:
    def __init__(self, presenter):
        self.presenter = presenter

    def initialize(self):
        initialize_canvas_presenter(self.presenter)

    def debug_log_gate(self):
        return debug_log_gate()

    def connect_event_handler_signals(self, event_handler):
        event_handler.mouse_press_event_on_image_label_signal.connect(
            self.presenter.image_label_handler.handle_mouse_press
        )
        event_handler.mouse_move_event_on_image_label_signal.connect(
            self.presenter.image_label_handler.handle_mouse_move
        )
        event_handler.mouse_release_event_on_image_label_signal.connect(
            self.presenter.image_label_handler.handle_mouse_release
        )
        event_handler.keyboard_press_event_signal.connect(
            self.presenter.image_label_handler.handle_key_press
        )
        event_handler.keyboard_release_event_signal.connect(
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

    def get_current_label_dimensions(self) -> tuple[int, int]:
        return get_current_label_dimensions(self.presenter)

    def update_minimum_window_size(self):
        return update_minimum_window_size(self.presenter)

    def invalidate_render_state(self, clear_magnifier: bool = False):
        return invalidate_render_state(self.presenter)

    def finish_resize_delay(self):
        return finish_resize_delay(self.presenter)

    def start_interactive_movement(self):
        return start_interactive_movement(self.presenter)

class CanvasViewCoordinator:
    def __init__(self, presenter):
        self.presenter = presenter

    def is_gl_canvas(self):
        return is_gl_canvas(self.presenter)

    def supports_legacy_gl_magnifier(self):
        return supports_legacy_gl_magnifier(self.presenter)

    def set_image_layers(
        self, background=None, magnifier=None, mag_pos=None, coords_snapshot=None
    ):
        return set_image_layers(
            self.presenter, background, magnifier, mag_pos, coords_snapshot
        )

    def prepare_gl_background_layers(self, image1, image2):
        return prepare_gl_background_layers(self.presenter, image1, image2)

    def display_single_image_on_label(self, pil_image: PIL.Image.Image | None):
        return display_single_image_on_label(self.presenter, pil_image)

    def sync_widget_overlay_coords(self):
        return sync_widget_overlay_coords(self.presenter)

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

    def ensure_images_unified(self, source1, source2):
        return ensure_images_unified(self.presenter, source1, source2)

    def ensure_images_scaled(self, w, h):
        return ensure_images_scaled(self.presenter, w, h)

    def start_scaling_worker(self, src1, src2, w, h):
        return start_scaling_worker(self.presenter, src1, src2, w, h)

    def on_display_scaling_ready(self, result):
        return on_display_scaling_ready(self.presenter, result)

    def should_use_dirty_rects_optimization(
        self, render_params_dict: dict, label_dims: tuple = None
    ) -> bool:
        return should_use_dirty_rects_optimization(
            self.presenter, render_params_dict, label_dims
        )

    def render_background(self, sig):
        return render_background(self.presenter, sig)

    def create_preview_cache_async(self, img1, img2):
        return create_preview_cache_async(self.presenter, img1, img2)

    def on_preview_cache_ready(self, result):
        return on_preview_cache_ready(self.presenter, result)

class CanvasMagnifierCoordinator:
    def __init__(self, presenter):
        self.presenter = presenter

    def get_signature(self):
        return get_magnifier_signature(self.presenter)

    def render_gl_fast(self):
        return render_magnifier_gl_fast(self.presenter)

    def render_diff_fallback(
        self, vp, orig1, orig2, diff_mode, slots, mag_px, border_color, radius, interp_key
    ):
        return render_magnifier_diff_fallback(
            self.presenter,
            vp,
            orig1,
            orig2,
            diff_mode,
            slots,
            mag_px,
            border_color,
            radius,
            interp_key,
        )

    def render_layer(self, sig) -> bool:
        return render_magnifier_layer(self.presenter, sig)

    def start_worker(
        self,
        render_params_dict: dict,
        image1_scaled_for_display,
        image2_scaled_for_display,
        original_image1_pil,
        original_image2_pil,
        magnifier_coords,
        label_width: int,
        label_height: int,
    ):
        return start_magnifier_only_worker(
            self.presenter,
            render_params_dict,
            image1_scaled_for_display,
            image2_scaled_for_display,
            original_image1_pil,
            original_image2_pil,
            magnifier_coords,
            label_width,
            label_height,
        )

    def render_capture_area_only_optimized(
        self,
        render_params_dict: dict,
        image1_scaled_for_display,
        image2_scaled_for_display,
        original_image1_pil,
        original_image2_pil,
        magnifier_coords,
        label_width: int,
        label_height: int,
    ):
        return render_capture_area_only_optimized(
            self.presenter,
            render_params_dict,
            image1_scaled_for_display,
            image2_scaled_for_display,
            original_image1_pil,
            original_image2_pil,
            magnifier_coords,
            label_width,
            label_height,
        )

    def on_capture_patch_ready(self, result):
        return on_capture_patch_ready(self.presenter, result)

    @staticmethod
    def worker_task(payload):
        return magnifier_worker_task(payload)

    def on_worker_error(self, error_tuple):
        return on_magnifier_worker_error(self.presenter, error_tuple)

    def on_layer_ready(self, result):
        return on_magnifier_layer_ready(self.presenter, result)

    def on_patch_ready(self, result):
        return on_magnifier_patch_ready(self.presenter, result)

    def update_widget_capture_area_geometry(self, magnifier_coords, w, h):
        return update_widget_capture_area_geometry(self.presenter, magnifier_coords, w, h)

    def stop_interactive_movement(self):
        return stop_interactive_movement_impl(
            self.presenter, self.presenter.lifecycle.debug_log_gate()
        )

    def update_capture_area_display(self):
        return update_capture_area_display_impl(self.presenter)

class CanvasResultCoordinator:
    def __init__(self, presenter):
        self.presenter = presenter

    def on_worker_finished(
        self, result_payload: dict, params: dict, finished_task_id: int
    ):
        return on_worker_finished(self.presenter, result_payload, params, finished_task_id)

    def handle_background_result(self, result: dict, params: dict):
        return handle_background_result(self.presenter, result, params)

    def handle_magnifier_result(self, result: dict, params: dict):
        return handle_magnifier_result(
            self.presenter, result, params, self.presenter.lifecycle.debug_log_gate()
        )

    def handle_legacy_result(self, result: dict, params: dict):
        return handle_legacy_result(
            self.presenter, result, params, self.presenter.lifecycle.debug_log_gate()
        )

    def on_worker_error(self, msg: str):
        return on_worker_error(self.presenter, msg)

    def on_generic_worker_error(self, error_tuple: tuple):
        return on_generic_worker_error(error_tuple)
