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


def get_diff_toast_message(presenter, diff_mode: str) -> str:
    current_language = getattr(presenter.store.settings, "current_language", "en")
    if diff_mode == "highlight":
        message = tr("msg.highlight_diff_in_progress", current_language)
        return (
            "Highlight diff..."
            if message == "msg.highlight_diff_in_progress"
            else message
        )
    if diff_mode == "grayscale":
        message = tr("msg.grayscale_diff_in_progress", current_language)
        return (
            "Grayscale diff..."
            if message == "msg.grayscale_diff_in_progress"
            else message
        )
    if diff_mode == "edges":
        message = tr("msg.edge_comparison_in_progress", current_language)
        return (
            "Edge comparison..."
            if message == "msg.edge_comparison_in_progress"
            else message
        )

    message = tr("msg.ssim_calculation_in_progress", current_language)
    return (
        "SSIM calculation..."
        if message == "msg.ssim_calculation_in_progress"
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
    if toast_manager is None or toast_id is None:
        presenter._active_diff_toast_id = None
        presenter._active_diff_toast_key = None
        return
    if getattr(presenter, "_active_diff_toast_key", None) != request_key:
        return

    diff_mode = getattr(presenter.store.viewport.view_state, "diff_mode", "off")
    current_language = getattr(presenter.store.settings, "current_language", "en")
    if diff_mode == "highlight":
        done_message = tr("msg.highlight_diff_done", current_language)
        if done_message == "msg.highlight_diff_done":
            done_message = "Highlight diff done"
    elif diff_mode == "grayscale":
        done_message = tr("msg.grayscale_diff_done", current_language)
        if done_message == "msg.grayscale_diff_done":
            done_message = "Grayscale diff done"
    elif diff_mode == "edges":
        done_message = tr("msg.edge_comparison_done", current_language)
        if done_message == "msg.edge_comparison_done":
            done_message = "Edge comparison done"
    else:
        done_message = tr("msg.ssim_calculation_done", current_language)
        if done_message == "msg.ssim_calculation_done":
            done_message = "SSIM done"

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
