import logging
import time

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QPainter

from ui.canvas_features.magnifier import iter_magnifier_models
from ui.widgets.gl_canvas.helpers import reset_canvas_overlays

from .common import get_live_image_label, start_pending_magnifier_layer

logger = logging.getLogger("ImproveImgSLI")

def _has_visible_magnifiers(presenter) -> bool:
    return any(
        bool(model.visible)
        for model in iter_magnifier_models(
            presenter.store.viewport.view_state,
            presenter.store.viewport.render_config,
        )
    )

def on_capture_patch_ready(presenter, result):
    if not result:
        return
    try:
        capture_patch_pil, patch_pos, task_id = result
        if task_id < presenter._last_displayed_task_id:
            return
        presenter._last_displayed_task_id = task_id
        if not capture_patch_pil:
            if presenter._cached_base_pixmap and not presenter._cached_base_pixmap.isNull():
                presenter.ui.image_label.setPixmap(presenter._cached_base_pixmap)
            return

        from shared.image_processing.qt_conversion import pil_to_qpixmap_optimized

        capture_pixmap = pil_to_qpixmap_optimized(capture_patch_pil, copy=False)
        if capture_pixmap.isNull():
            return
        if presenter._cached_base_pixmap and not presenter._cached_base_pixmap.isNull():
            result_pixmap = presenter._cached_base_pixmap.copy()
            painter = QPainter(result_pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawPixmap(patch_pos, capture_pixmap)
            painter.end()
            presenter.ui.image_label.setPixmap(result_pixmap)
            presenter.current_displayed_pixmap = result_pixmap
    except Exception as exc:
        logger.error("Error displaying capture area patch: %s", exc, exc_info=True)

def on_magnifier_worker_error(presenter, error_tuple):
    presenter._is_magnifier_worker_running = False
    presenter._active_magnifier_task_id = 0
    presenter._active_magnifier_request_seq = 0
    presenter._active_magnifier_signature = None
    presenter._active_magnifier_started_at = 0.0
    exctype, value, traceback_str = error_tuple
    error_msg = f"{exctype.__name__}: {value}"
    if traceback_str:
        logger.error("[RENDER] Magnifier worker error: %s\n%s", error_msg, traceback_str)
    else:
        logger.error("[RENDER] Magnifier worker error: %s", error_msg)
    if presenter._magnifier_update_pending:
        start_pending_magnifier_layer(presenter)

def on_magnifier_layer_ready(presenter, result):
    data, task_id = result
    active_task_id = getattr(presenter, "_active_magnifier_task_id", 0)
    started_at = getattr(presenter, "_active_magnifier_started_at", 0.0)
    _age_ms = max(0.0, (time.monotonic() - started_at) * 1000.0) if started_at else 0.0
    presenter._is_magnifier_worker_running = False
    presenter._active_magnifier_task_id = 0
    presenter._active_magnifier_request_seq = 0
    presenter._active_magnifier_signature = None
    presenter._active_magnifier_started_at = 0.0

    if active_task_id and task_id != active_task_id:
        if presenter._magnifier_update_pending:
            start_pending_magnifier_layer(presenter)
        return

    if task_id < presenter._last_displayed_task_id:
        if presenter._magnifier_update_pending:
            start_pending_magnifier_layer(presenter)
        return
    presenter._last_displayed_task_id = task_id

    from shared.image_processing.qt_conversion import pil_to_qpixmap_optimized

    mag_patch = data.get("magnifier_patch")
    mag_pos = data.get("magnifier_patch_top_left")
    mag_pixmap = pil_to_qpixmap_optimized(mag_patch, copy=False) if mag_patch else None

    if not mag_pixmap or mag_pixmap.isNull() or not mag_pos:
        image_label = get_live_image_label(presenter)
        if image_label is None:
            if presenter._magnifier_update_pending:
                start_pending_magnifier_layer(presenter)
            return
        image_label.set_magnifier_content(None, None)
    else:
        image_label = get_live_image_label(presenter)
        if image_label is None:
            if presenter._magnifier_update_pending:
                start_pending_magnifier_layer(presenter)
            return
        label_w, label_h = presenter.get_current_label_dimensions()
        pix_w, pix_h = presenter.store.viewport.geometry_state.pixmap_width, presenter.store.viewport.geometry_state.pixmap_height
        offset_x = (label_w - pix_w) // 2
        offset_y = (label_h - pix_h) // 2
        final_mag_pos_screen = QPoint(offset_x + mag_pos.x(), offset_y + mag_pos.y())
        image_label.set_magnifier_content(mag_pixmap, final_mag_pos_screen)

    if presenter._magnifier_update_pending:
        start_pending_magnifier_layer(presenter)

def on_magnifier_patch_ready(presenter, result):
    if not result:
        return
    try:
        magnifier_patch_pil, mag_pos_on_image, task_id, used_coords = result
        if task_id < presenter._last_displayed_task_id:
            return
        presenter._last_displayed_task_id = task_id
        if not magnifier_patch_pil or not mag_pos_on_image:
            return

        from shared.image_processing.qt_conversion import pil_to_qpixmap_optimized

        magnifier_pixmap = pil_to_qpixmap_optimized(magnifier_patch_pil, copy=False)
        if magnifier_pixmap.isNull():
            return

        presenter.view.sync_widget_overlay_coords()
        label_w, label_h = presenter.get_current_label_dimensions()
        pix_w, pix_h = presenter.store.viewport.geometry_state.pixmap_width, presenter.store.viewport.geometry_state.pixmap_height
        offset_x = (label_w - pix_w) // 2
        offset_y = (label_h - pix_h) // 2
        mag_pos_on_label = QPoint(offset_x + mag_pos_on_image.x(), offset_y + mag_pos_on_image.y())

        image_label = get_live_image_label(presenter)
        if image_label is None:
            return
        image_label.set_magnifier_content(magnifier_pixmap, mag_pos_on_label)
    except Exception as exc:
        logger.error("Error displaying magnifier patch: %s", exc, exc_info=True)

def update_widget_capture_area_geometry(presenter, magnifier_coords, w, h):
    presenter.view.sync_widget_overlay_coords()

def stop_interactive_movement(presenter, log_gate):
    presenter.store.viewport.interaction_state.is_interactive_mode = False
    presenter._cached_split_pos = -1.0
    presenter._last_mag_signature = None
    image_label = get_live_image_label(presenter)

    if not _has_visible_magnifiers(presenter):
        if presenter.view.is_gl_canvas():
            if image_label is not None:
                reset_canvas_overlays(image_label)
        else:
            presenter.view.sync_widget_overlay_coords()
    else:
        presenter.view.sync_widget_overlay_coords()
    presenter.schedule_update()

def update_capture_area_display(presenter):
    if _has_visible_magnifiers(presenter):
        presenter.view.sync_widget_overlay_coords()
