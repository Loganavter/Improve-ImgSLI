from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QPixmap

from events.image_label_event_handler import ImageLabelEventHandler
from events.window_event_handler import WindowEventHandler
from tabs.image_compare.canvas.helpers import clear_canvas_diff_source, get_canvas

_last_debug_log_time = 0
_debug_log_interval = 1.0


def initialize_canvas_presenter(presenter) -> None:
    presenter.image_label_handler = ImageLabelEventHandler(
        presenter.store, presenter.main_controller, presenter
    )
    presenter.window_handler = WindowEventHandler(
        presenter.store,
        presenter.main_controller,
        presenter.widget,
        presenter.main_window_app,
    )

    presenter.current_displayed_pixmap: QPixmap | None = None
    presenter.current_rendering_task_id = 0
    presenter.current_scaling_task_id = 0
    presenter._display_cache_request_key = None
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
    presenter._is_magnifier_worker_running = False
    presenter._magnifier_update_pending = False
    presenter._magnifier_request_seq = 0
    presenter._active_magnifier_task_id = 0
    presenter._active_magnifier_request_seq = 0
    presenter._active_magnifier_signature = None
    presenter._active_magnifier_started_at = 0.0
    presenter._pending_magnifier_signature = None
    presenter._pending_magnifier_request_seq = 0
    presenter._pending_magnifier_requested_at = 0.0
    presenter._pending_cached_diff_request_key = None
    presenter._active_diff_toast_id = None
    presenter._active_diff_toast_key = None

    presenter._update_scheduler_timer = QTimer(presenter)
    presenter._update_scheduler_timer.setSingleShot(True)
    target_fps = getattr(presenter.store.settings, "video_recording_fps", 60)
    target_fps = max(10, min(144, target_fps))
    presenter._update_scheduler_timer.setInterval(int(1000 / target_fps))
    presenter._update_scheduler_timer.timeout.connect(
        presenter.update_comparison_if_needed
    )


def debug_log_gate():
    return {
        "last": _last_debug_log_time,
        "interval": _debug_log_interval,
        "time_fn": time.time,
        "setter": lambda value: globals().__setitem__("_last_debug_log_time", value),
    }


def get_current_label_dimensions(presenter) -> tuple[int, int]:
    canvas = get_canvas(presenter.widget)
    if canvas is not None:
        size = canvas.size()
        return (size.width(), size.height())
    return (0, 0)


def update_minimum_window_size(presenter):
    main_window = presenter.main_window_app
    if not getattr(main_window, "_is_ui_stable", False):
        return

    from ui.layout_geometry import apply_main_window_minimum

    apply_main_window_minimum(main_window)


def invalidate_render_state(presenter):
    presenter._last_bg_signature = None
    presenter._last_mag_signature = None
    presenter._last_img_sig = None
    presenter._cached_base_pixmap = None
    presenter.current_displayed_pixmap = None
    presenter._pending_interactive_mode = None
    presenter._pending_cached_diff_request_key = None
    presenter._active_diff_toast_key = None
    toast_manager = getattr(presenter.main_window_app, "toast_manager", None)
    active_toast_id = getattr(presenter, "_active_diff_toast_id", None)
    if toast_manager is not None and active_toast_id is not None:
        try:
            toast_manager.close_toast(active_toast_id)
        except Exception:
            pass
    presenter._active_diff_toast_id = None

    image_label = get_canvas(getattr(presenter, "widget", None))
    if image_label is not None:
        clear_canvas_diff_source(image_label)


def start_interactive_movement(presenter):
    if not presenter.store.viewport.view_state.optimize_interactive_movement:
        presenter.store.viewport.interaction_state.is_interactive_mode = False
        presenter.store.emit_state_change()
        if presenter.main_controller is not None:
            presenter.main_controller.update_requested.emit()
        return
    presenter.store.viewport.interaction_state.is_interactive_mode = True
    presenter.schedule_update()
