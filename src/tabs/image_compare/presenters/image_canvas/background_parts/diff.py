from tabs.image_compare.canvas.helpers import get_canvas_widget

from .diff_toasts import dismiss_active_diff_toast


def sync_diff_texture(presenter, diff_mode):
    image_label = get_canvas_widget(getattr(presenter, "ui", None))
    if image_label is None:
        return

    if (
        diff_mode != "ssim"
        and getattr(presenter, "_active_diff_toast_id", None) is not None
    ):
        dismiss_active_diff_toast(presenter)

    current_uploaded_diff = getattr(image_label, "_diff_source_pil_image", None)
    if diff_mode != "ssim":
        if current_uploaded_diff is not None:
            image_label.upload_diff_source_pil_image(None)
        return

    cached_diff_image = getattr(
        presenter.store.viewport.session_data.render_cache, "cached_diff_image", None
    )
    current_uploaded_id = (
        None if current_uploaded_diff is None else id(current_uploaded_diff)
    )
    target_diff_id = None if cached_diff_image is None else id(cached_diff_image)

    if cached_diff_image is not None and current_uploaded_id != target_diff_id:
        image_label.upload_diff_source_pil_image(cached_diff_image)
