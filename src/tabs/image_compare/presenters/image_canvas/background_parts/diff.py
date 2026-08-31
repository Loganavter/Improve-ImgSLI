from shared.rendering.image_identity import image_uid
from tabs.image_compare.canvas.helpers import get_canvas_widget

from .diff_toasts import dismiss_active_diff_toast


def sync_diff_texture(presenter, diff_mode):
    image_label = get_canvas_widget(getattr(presenter, "widget", None))
    if image_label is None:
        return

    if (
        diff_mode != "ssim"
        and getattr(presenter, "_active_diff_toast_id", None) is not None
    ):
        dismiss_active_diff_toast(presenter)

    current_uploaded_diff = getattr(image_label, "_diff_source_pil_image", None)
    if diff_mode != "ssim":
        # Keep stale diff_source while source images not ready (sync shader modes
        # highlight/grayscale/edges compute shader from sources; clearing too early flashes)
        if not bool(getattr(image_label, "_source_images_ready", False)):
            return
        if current_uploaded_diff is not None:
            image_label.upload_diff_source_pil_image(None)
        return

    cached_diff_image = getattr(
        presenter.store.viewport.session_data.render_cache, "cached_diff_image", None
    )
    # image_uid, not id(): see the source_ids comment in
    # rhi_renderer/__init__.py for why -- a GC'd diff image's freed address
    # could otherwise collide with a fresh one and skip an upload that was
    # actually needed.
    current_uploaded_id = (
        None if current_uploaded_diff is None else image_uid(current_uploaded_diff)
    )
    target_diff_id = None if cached_diff_image is None else image_uid(cached_diff_image)

    if cached_diff_image is not None and current_uploaded_id != target_diff_id:
        image_label.upload_diff_source_pil_image(cached_diff_image)
