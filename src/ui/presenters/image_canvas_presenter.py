import time

import PIL.Image
from PyQt6.QtCore import (
    QObject,
    QPoint,
    QSize,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QSizePolicy

from core.store import Store
from events.image_label_event_handler import ImageLabelEventHandler
from events.window_event_handler import WindowEventHandler
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
from ui.presenters.image_canvas.magnifier import (
    on_capture_patch_ready,
    on_magnifier_layer_ready,
    on_magnifier_patch_ready,
    on_magnifier_worker_error,
    render_capture_area_only_optimized,
    render_magnifier_gl_fast,
    render_magnifier_layer,
    render_magnifier_ssim_fallback,
    start_magnifier_only_worker,
    stop_interactive_movement as stop_interactive_movement_impl,
    sync_widget_overlay_coords,
    update_capture_area_display as update_capture_area_display_impl,
    update_widget_capture_area_geometry,
    magnifier_worker_task,
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
)

_last_debug_log_time = 0
_debug_log_interval = 1.0

class ImageCanvasPresenter(QObject):

    _worker_finished_signal = pyqtSignal(dict, dict, int)
    _worker_error_signal = pyqtSignal(str)

    def __init__(self, store: Store, main_controller, ui, main_window_app, parent=None):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.ui = ui
        self.main_window_app = main_window_app

        self.image_label_handler = ImageLabelEventHandler(store, main_controller, self)
        self.window_handler = WindowEventHandler(
            store, main_controller, ui, main_window_app
        )

        self.current_displayed_pixmap: QPixmap | None = None
        self.current_rendering_task_id = 0
        self.current_scaling_task_id = 0
        self._last_displayed_task_id = 0

        self._cached_base_pixmap: QPixmap | None = None

        self._last_bg_signature = None
        self._last_mag_signature = None

        self._cached_split_pos: float = -1.0
        self._cached_render_params: tuple | None = None
        self._last_magnifier_pos: QPoint | None = None
        self._last_capture_pos: QPoint | None = None
        self._last_label_dims: tuple | None = None

        self._pending_interactive_mode: bool | None = None
        self._is_generating_background: bool = False
        self._is_magnifier_worker_running: bool = False
        self._magnifier_update_pending: bool = False

        self._update_scheduler_timer = QTimer(self)
        self._update_scheduler_timer.setSingleShot(True)

        target_fps = getattr(self.store.settings, "video_recording_fps", 60)
        target_fps = max(10, min(144, target_fps))
        interval = int(1000 / target_fps)
        self._update_scheduler_timer.setInterval(interval)
        self._update_scheduler_timer.timeout.connect(self.update_comparison_if_needed)

        self._worker_finished_signal.connect(self._on_worker_finished)
        self._worker_error_signal.connect(self._on_worker_error)

    def _is_gl_canvas(self):
        return is_gl_canvas(self)

    def _debug_log_gate(self):
        return {
            "last": _last_debug_log_time,
            "interval": _debug_log_interval,
            "time_fn": time.time,
            "setter": lambda value: globals().__setitem__("_last_debug_log_time", value),
        }

    def _set_image_layers(
        self, background=None, magnifier=None, mag_pos=None, coords_snapshot=None
    ):
        return set_image_layers(self, background, magnifier, mag_pos, coords_snapshot)

    def _prepare_gl_background_layers(self, image1, image2):
        return prepare_gl_background_layers(self, image1, image2)

    def connect_event_handler_signals(self, event_handler):
        event_handler.mouse_press_event_on_image_label_signal.connect(
            self.image_label_handler.handle_mouse_press
        )
        event_handler.mouse_move_event_on_image_label_signal.connect(
            self.image_label_handler.handle_mouse_move
        )
        event_handler.mouse_release_event_on_image_label_signal.connect(
            self.image_label_handler.handle_mouse_release
        )
        event_handler.keyboard_press_event_signal.connect(
            self.image_label_handler.handle_key_press
        )
        event_handler.keyboard_release_event_signal.connect(
            self.image_label_handler.handle_key_release
        )
        event_handler.mouse_wheel_event_on_image_label_signal.connect(
            self.image_label_handler.handle_wheel_scroll
        )
        event_handler.drag_enter_event_signal.connect(
            self.window_handler.handle_drag_enter
        )
        event_handler.drag_move_event_signal.connect(
            self.window_handler.handle_drag_move
        )
        event_handler.drag_leave_event_signal.connect(
            self.window_handler.handle_drag_leave
        )
        event_handler.drop_event_signal.connect(self.window_handler.handle_drop)
        event_handler.resize_event_signal.connect(self.window_handler.handle_resize)
        event_handler.close_event_signal.connect(self.window_handler.handle_close)

    def get_current_label_dimensions(self) -> tuple[int, int]:
        if hasattr(self.ui, "image_label"):
            size = self.ui.image_label.size()
            return (size.width(), size.height())
        return (0, 0)

    def update_minimum_window_size(self):
        if not getattr(self.main_window_app, "_is_ui_stable", False):
            return

        layout = self.main_window_app.layout()
        if not layout or not hasattr(self.ui, "image_label"):
            return

        original_policy = self.ui.image_label.sizePolicy()
        temp_policy = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        temp_policy.setHeightForWidth(original_policy.hasHeightForWidth())
        temp_policy.setWidthForHeight(original_policy.hasWidthForHeight())
        temp_policy.setVerticalPolicy(
            QSizePolicy.Policy.Preferred
            if original_policy.verticalPolicy() != QSizePolicy.Policy.Ignored
            else QSizePolicy.Policy.Ignored
        )
        temp_policy.setHorizontalPolicy(
            QSizePolicy.Policy.Preferred
            if original_policy.horizontalPolicy() != QSizePolicy.Policy.Ignored
            else QSizePolicy.Policy.Ignored
        )

        try:
            self.ui.image_label.setSizePolicy(temp_policy)
            self.ui.image_label.updateGeometry()
            if layout:
                layout.invalidate()
                layout.activate()

            layout_hint_size = layout.sizeHint() if layout else QSize(250, 300)
            base_min_w, base_min_h = (250, 300)
            new_min_w = max(base_min_w, layout_hint_size.width())
            new_min_h = max(base_min_h, layout_hint_size.height())
            padding = 10
            new_min_w += padding
            new_min_h += padding
            current_min = self.main_window_app.minimumSize()
            if current_min.width() != new_min_w or current_min.height() != new_min_h:
                self.main_window_app.setMinimumSize(new_min_w, new_min_h)
        finally:
            if (
                hasattr(self.ui, "image_label")
                and self.ui.image_label.sizePolicy() != original_policy
            ):
                self.ui.image_label.setSizePolicy(original_policy)
                self.ui.image_label.updateGeometry()
                if layout:
                    layout.invalidate()
                    layout.activate()

    def schedule_update(self):
        return schedule_update_impl(self)

    def invalidate_render_state(self, clear_magnifier: bool = False):
        self._last_bg_signature = None
        self._last_mag_signature = None
        self._gl_last_img_sig = None
        self._cached_base_pixmap = None
        self.current_displayed_pixmap = None
        self._pending_interactive_mode = None

    def update_comparison_if_needed(self) -> bool:
        return update_comparison_if_needed_impl(self)

    def _get_render_params_signature(self, s1, s2):
        return get_render_params_signature(self, s1, s2)

    def _get_background_signature(self, s1, s2):
        return get_background_signature(self, s1, s2)

    def _get_magnifier_signature(self):
        return get_magnifier_signature(self)

    def _ensure_images_unified(self, source1, source2):
        return ensure_images_unified(self, source1, source2)

    def _ensure_images_scaled(self, w, h):
        return ensure_images_scaled(self, w, h)

    def _start_scaling_worker(self, src1, src2, w, h):
        return start_scaling_worker(self, src1, src2, w, h)

    @pyqtSlot(object)
    def _on_display_scaling_ready(self, result):
        return on_display_scaling_ready(self, result)

    def _should_use_dirty_rects_optimization(
        self, render_params_dict: dict, label_dims: tuple = None
    ) -> bool:
        return should_use_dirty_rects_optimization(self, render_params_dict, label_dims)

    def _render_background(self, sig):
        return render_background(self, sig)

    def _sync_widget_overlay_coords(self):
        return sync_widget_overlay_coords(self)

    def _render_magnifier_gl_fast(self):
        return render_magnifier_gl_fast(self)

    def _render_magnifier_ssim_fallback(
        self, vp, orig1, orig2, cap_x, cap_y, cap_half_img,
        slots, mag_px, border_color, radius,
    ):
        return render_magnifier_ssim_fallback(
            self, vp, orig1, orig2, cap_x, cap_y, cap_half_img, slots, mag_px, border_color, radius
        )

    def _get_divider_color_tuple(self, vp):
        return get_divider_color_tuple(vp)

    def _render_magnifier_layer(self, sig) -> bool:
        return render_magnifier_layer(self, sig)

    def _start_magnifier_only_worker(
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
            self,
            render_params_dict,
            image1_scaled_for_display,
            image2_scaled_for_display,
            original_image1_pil,
            original_image2_pil,
            magnifier_coords,
            label_width,
            label_height,
        )

    def _render_capture_area_only_optimized(
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
            self,
            render_params_dict,
            image1_scaled_for_display,
            image2_scaled_for_display,
            original_image1_pil,
            original_image2_pil,
            magnifier_coords,
            label_width,
            label_height,
        )

    @pyqtSlot(object)
    def _on_capture_patch_ready(self, result):
        return on_capture_patch_ready(self, result)

    @staticmethod
    def _magnifier_worker_task(payload):
        return magnifier_worker_task(payload)

    @pyqtSlot(object)
    def _on_magnifier_worker_error(self, error_tuple):
        return on_magnifier_worker_error(self, error_tuple)

    @pyqtSlot(object)
    def _on_magnifier_layer_ready(self, result):
        return on_magnifier_layer_ready(self, result)

    @pyqtSlot(object)
    def _on_magnifier_patch_ready(self, result):
        return on_magnifier_patch_ready(self, result)

    @pyqtSlot(dict, dict, int)
    def _on_worker_finished(
        self, result_payload: dict, params: dict, finished_task_id: int
    ):
        return on_worker_finished(self, result_payload, params, finished_task_id)

    def _handle_background_result(self, result: dict, params: dict):
        return handle_background_result(self, result, params)

    def _handle_magnifier_result(self, result: dict, params: dict):
        return handle_magnifier_result(self, result, params, self._debug_log_gate())

    def _handle_legacy_result(self, result: dict, params: dict):
        return handle_legacy_result(self, result, params, self._debug_log_gate())

    @pyqtSlot(str)
    def _on_worker_error(self, msg: str):
        return on_worker_error(self, msg)

    @pyqtSlot(tuple)
    def _on_generic_worker_error(self, error_tuple: tuple):
        return on_generic_worker_error(error_tuple)

    def _display_single_image_on_label(self, pil_image: PIL.Image.Image | None):
        return display_single_image_on_label(self, pil_image)

    def _create_preview_cache_async(self, img1, img2):
        return create_preview_cache_async(self, img1, img2)

    @pyqtSlot(object)
    def _on_preview_cache_ready(self, result):
        return on_preview_cache_ready(self, result)

    def _finish_resize_delay(self):
        return finish_resize_delay(self)

    def _update_widget_capture_area_geometry(self, magnifier_coords, w, h):
        return update_widget_capture_area_geometry(self, magnifier_coords, w, h)

    def start_interactive_movement(self):
        if not self.store.viewport.optimize_magnifier_movement:
            self.store.viewport.is_interactive_mode = False
            self.store.emit_state_change()
            if hasattr(self, "main_controller") and self.main_controller is not None:
                self.main_controller.update_requested.emit()
            return
        self.store.viewport.is_interactive_mode = True
        self.schedule_update()

    def stop_interactive_movement(self):
        return stop_interactive_movement_impl(self, self._debug_log_gate())

    def update_capture_area_display(self):
        return update_capture_area_display_impl(self)
