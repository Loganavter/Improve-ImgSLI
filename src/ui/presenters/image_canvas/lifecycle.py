from __future__ import annotations

import time

from PyQt6.QtCore import QPoint, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QSizePolicy

from events.image_label_event_handler import ImageLabelEventHandler
from events.window_event_handler import WindowEventHandler

_last_debug_log_time = 0
_debug_log_interval = 1.0

def initialize_canvas_presenter(presenter) -> None:
    presenter.image_label_handler = ImageLabelEventHandler(
        presenter.store, presenter.main_controller, presenter
    )
    presenter.window_handler = WindowEventHandler(
        presenter.store, presenter.main_controller, presenter.ui, presenter.main_window_app
    )

    presenter.current_displayed_pixmap: QPixmap | None = None
    presenter.current_rendering_task_id = 0
    presenter.current_scaling_task_id = 0
    presenter._last_displayed_task_id = 0
    presenter._cached_base_pixmap: QPixmap | None = None
    presenter._last_bg_signature = None
    presenter._last_mag_signature = None
    presenter._cached_split_pos = -1.0
    presenter._cached_render_params = None
    presenter._last_magnifier_pos: QPoint | None = None
    presenter._last_capture_pos: QPoint | None = None
    presenter._last_label_dims = None
    presenter._pending_interactive_mode = None
    presenter._is_generating_background = False
    presenter._is_magnifier_worker_running = False
    presenter._magnifier_update_pending = False
    presenter._cached_gl_background_layers_key = None
    presenter._cached_gl_background_layers = None
    presenter._cached_gl_diff_image_key = None
    presenter._cached_gl_diff_image = None
    presenter._pending_gl_background_layers_key = None
    presenter._pending_gl_background_layers_started_at = None
    presenter._pending_cached_diff_request_key = None
    presenter._pending_magnifier_cached_diff_request_key = None
    presenter._magnifier_cached_diff_request_key = None
    presenter._magnifier_cached_diff_image = None
    presenter._active_diff_toast_id = None
    presenter._active_diff_toast_key = None

    presenter._update_scheduler_timer = QTimer(presenter)
    presenter._update_scheduler_timer.setSingleShot(True)
    target_fps = getattr(presenter.store.settings, "video_recording_fps", 60)
    target_fps = max(10, min(144, target_fps))
    presenter._update_scheduler_timer.setInterval(int(1000 / target_fps))
    presenter._update_scheduler_timer.timeout.connect(presenter.update_comparison_if_needed)

def debug_log_gate():
    return {
        "last": _last_debug_log_time,
        "interval": _debug_log_interval,
        "time_fn": time.time,
        "setter": lambda value: globals().__setitem__("_last_debug_log_time", value),
    }

def get_current_label_dimensions(presenter) -> tuple[int, int]:
    if hasattr(presenter.ui, "image_label"):
        size = presenter.ui.image_label.size()
        return (size.width(), size.height())
    return (0, 0)

def update_minimum_window_size(presenter):
    if not getattr(presenter.main_window_app, "_is_ui_stable", False):
        return

    layout = presenter.main_window_app.layout()
    if not layout or not hasattr(presenter.ui, "image_label"):
        return

    original_policy = presenter.ui.image_label.sizePolicy()
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
        presenter.ui.image_label.setSizePolicy(temp_policy)
        presenter.ui.image_label.updateGeometry()
        layout.invalidate()
        layout.activate()

        layout_hint_size = layout.sizeHint()
        new_min_w = max(250, layout_hint_size.width()) + 10
        new_min_h = max(300, layout_hint_size.height()) + 10
        current_min = presenter.main_window_app.minimumSize()
        if current_min.width() != new_min_w or current_min.height() != new_min_h:
            presenter.main_window_app.setMinimumSize(new_min_w, new_min_h)
    finally:
        if presenter.ui.image_label.sizePolicy() != original_policy:
            presenter.ui.image_label.setSizePolicy(original_policy)
            presenter.ui.image_label.updateGeometry()
            layout.invalidate()
            layout.activate()

def invalidate_render_state(presenter):
    presenter._last_bg_signature = None
    presenter._last_mag_signature = None
    presenter._gl_last_img_sig = None
    presenter._cached_base_pixmap = None
    presenter.current_displayed_pixmap = None
    presenter._pending_interactive_mode = None
    presenter._cached_gl_background_layers_key = None
    presenter._cached_gl_background_layers = None
    presenter._cached_gl_diff_image_key = None
    presenter._cached_gl_diff_image = None
    presenter._pending_gl_background_layers_key = None
    presenter._pending_gl_background_layers_started_at = None
    presenter._pending_cached_diff_request_key = None
    presenter._pending_magnifier_cached_diff_request_key = None
    presenter._magnifier_cached_diff_request_key = None
    presenter._magnifier_cached_diff_image = None
    presenter._active_diff_toast_key = None
    toast_manager = getattr(presenter.main_window_app, "toast_manager", None)
    active_toast_id = getattr(presenter, "_active_diff_toast_id", None)
    if toast_manager is not None and active_toast_id is not None:
        try:
            toast_manager.close_toast(active_toast_id)
        except Exception:
            pass
    presenter._active_diff_toast_id = None

    image_label = getattr(getattr(presenter, "ui", None), "image_label", None)
    if image_label is not None and hasattr(image_label, "upload_diff_source_pil_image"):
        image_label.upload_diff_source_pil_image(None)

def start_interactive_movement(presenter):
    if not presenter.store.viewport.view_state.optimize_magnifier_movement:
        presenter.store.viewport.interaction_state.is_interactive_mode = False
        presenter.store.emit_state_change()
        if presenter.main_controller is not None:
            presenter.main_controller.update_requested.emit()
        return
    presenter.store.viewport.interaction_state.is_interactive_mode = True
    presenter.schedule_update()
