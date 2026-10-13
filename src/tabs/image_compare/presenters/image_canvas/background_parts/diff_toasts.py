import logging

from sli_ui_toolkit.i18n import tr

logger = logging.getLogger("ImproveImgSLI")


def dismiss_active_diff_toast(presenter):
    toast_manager = getattr(presenter.main_window_app, "toast_manager", None)
    toast_id = getattr(presenter, "_active_diff_toast_id", None)
    if toast_manager is not None and toast_id is not None:
        try:
            toast_manager.close_toast(toast_id)
        except Exception:
            logger.exception("Failed to close SSIM toast")
    presenter._active_diff_toast_id = None
    presenter._active_diff_toast_key = None


def _current_language(owner) -> str:
    # Accept either a presenter/widget (owner.store) or a Store directly so
    # service callers (MetricsService) can reuse this builder without a
    # GUI-layer presenter.
    store = getattr(owner, "store", None)
    if store is None:
        store = owner
    settings = getattr(store, "settings", None)
    return getattr(settings, "current_language", "en")


def get_diff_toast_message(presenter, diff_mode: str, state: str = "in_progress") -> str:
    current_language = _current_language(presenter)
    # All SSIM/diff toast text is built here (single owner); metrics.py and
    # other sites call this instead of re-deriving wording. `state` selects
    # the in-progress / done / failed phase so one builder covers every site.
    if state == "done":
        if diff_mode == "highlight":
            message = tr("image_compare.msg.highlight_diff_done", current_language)
            return (
                "Highlight diff done"
                if message == "image_compare.msg.highlight_diff_done"
                else message
            )
        if diff_mode == "grayscale":
            message = tr("image_compare.msg.grayscale_diff_done", current_language)
            return (
                "Grayscale diff done"
                if message == "image_compare.msg.grayscale_diff_done"
                else message
            )
        if diff_mode == "edges":
            message = tr("image_compare.msg.edge_comparison_done", current_language)
            return (
                "Edge comparison done"
                if message == "image_compare.msg.edge_comparison_done"
                else message
            )
        message = tr("image_compare.msg.ssim_calculation_done", current_language)
        return (
            "SSIM done"
            if message == "image_compare.msg.ssim_calculation_done"
            else message
        )
    if state == "failed":
        message = tr("image_compare.msg.ssim_calculation_failed", current_language)
        return (
            "SSIM failed"
            if message == "image_compare.msg.ssim_calculation_failed"
            else message
        )

    # in progress
    if diff_mode == "highlight":
        message = tr("image_compare.msg.highlight_diff_in_progress", current_language)
        return (
            "Highlight diff..."
            if message == "image_compare.msg.highlight_diff_in_progress"
            else message
        )
    if diff_mode == "grayscale":
        message = tr("image_compare.msg.grayscale_diff_in_progress", current_language)
        return (
            "Grayscale diff..."
            if message == "image_compare.msg.grayscale_diff_in_progress"
            else message
        )
    if diff_mode == "edges":
        message = tr("image_compare.msg.edge_comparison_in_progress", current_language)
        return (
            "Edge comparison..."
            if message == "image_compare.msg.edge_comparison_in_progress"
            else message
        )

    message = tr("image_compare.msg.ssim_calculation_in_progress", current_language)
    return (
        "SSIM calculation..."
        if message == "image_compare.msg.ssim_calculation_in_progress"
        else message
    )


def format_diff_toast_message(presenter, diff_mode: str, progress_payload=None) -> str:
    return get_diff_toast_message(presenter, diff_mode)


def show_or_reuse_diff_toast(presenter, diff_mode, request_key):
    if diff_mode not in {"highlight", "grayscale", "ssim", "edges"}:
        return

    toast_manager = getattr(presenter.main_window_app, "toast_manager", None)
    if toast_manager is None:
        return

    if getattr(presenter, "_active_diff_toast_key", None) == request_key:
        return

    existing_toast_id = getattr(presenter, "_active_diff_toast_id", None)
    if existing_toast_id is not None:
        try:
            toast_manager.close_toast(existing_toast_id)
        except Exception:
            logger.exception("Failed to replace SSIM toast")

    try:
        toast_id = toast_manager.show_toast(
            format_diff_toast_message(presenter, diff_mode),
            duration=0,
            progress=0,
        )
        presenter._active_diff_toast_id = toast_id
        presenter._active_diff_toast_key = request_key
    except Exception:
        logger.exception("Failed to show SSIM toast")


def update_diff_toast_progress(presenter, request_key, progress_payload):
    toast_manager = getattr(presenter.main_window_app, "toast_manager", None)
    toast_id = getattr(presenter, "_active_diff_toast_id", None)
    if toast_manager is None or toast_id is None:
        return
    if getattr(presenter, "_active_diff_toast_key", None) != request_key:
        return

    diff_mode = getattr(presenter.store.viewport.view_state, "diff_mode", "off")
    progress_value = progress_payload
    if isinstance(progress_payload, dict):
        progress_value = progress_payload.get("progress", 0)

    try:
        toast_manager.update_toast(
            toast_id,
            format_diff_toast_message(
                presenter,
                diff_mode,
                progress_payload=progress_payload,
            ),
            success=False,
            duration=0,
            progress=progress_value,
        )
    except Exception:
        logger.exception("Failed to update diff toast progress")


def complete_diff_toast(presenter, request_key):
    toast_manager = getattr(presenter.main_window_app, "toast_manager", None)
    toast_id = getattr(presenter, "_active_diff_toast_id", None)
    if toast_id is None:
        presenter._active_diff_toast_id = None
        presenter._active_diff_toast_key = None
        return
    if toast_manager is None:
        # No manager to close with — keep the id so a later manager can close it.
        return
    if getattr(presenter, "_active_diff_toast_key", None) != request_key:
        try:
            toast_manager.close_toast(toast_id)
        except Exception:
            logger.exception("Failed to close stale diff toast")
            return
        presenter._active_diff_toast_id = None
        presenter._active_diff_toast_key = None
        return

    diff_mode = getattr(presenter.store.viewport.view_state, "diff_mode", "off")
    done_message = get_diff_toast_message(presenter, diff_mode, state="done")

    try:
        toast_manager.update_toast(
            toast_id,
            done_message,
            success=True,
            duration=2000,
            progress=100,
        )
    except Exception:
        logger.exception("Failed to complete diff toast")
    finally:
        presenter._active_diff_toast_id = None
        presenter._active_diff_toast_key = None
