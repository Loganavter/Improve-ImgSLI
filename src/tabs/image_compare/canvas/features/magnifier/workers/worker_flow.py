import logging

logger = logging.getLogger("ImproveImgSLI")


def render_magnifier_layer(presenter, sig):
    if not presenter._cached_base_pixmap:
        return False
    if sig == getattr(presenter, "_last_mag_signature", None):
        return True
    presenter._is_magnifier_worker_running = False
    presenter._magnifier_update_pending = False
    presenter._pending_magnifier_signature = None
    presenter._pending_magnifier_request_seq = 0
    presenter._pending_magnifier_requested_at = 0.0
    presenter._active_magnifier_task_id = 0
    presenter._active_magnifier_request_seq = 0
    presenter._active_magnifier_signature = None
    presenter.overlay.rebuild_overlay()
    presenter._last_mag_signature = (
        sig,
        getattr(presenter.widget.image_label, "_source_images_ready", False),
        tuple(getattr(presenter.widget.image_label, "_source_image_ids", []) or []),
    )
    return True
