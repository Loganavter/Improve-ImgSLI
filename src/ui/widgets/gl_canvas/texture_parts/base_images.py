from PIL import Image as PilImage
from PySide6.QtGui import QImage

from .upload_queue import queue_texture_upload

def upload_image(widget, qimage: QImage, slot_index: int):
    state = widget.runtime_state
    if slot_index not in (0, 1) or qimage.isNull():
        return

    state._images_uploaded[slot_index] = True

    converted_img = qimage.convertToFormat(QImage.Format.Format_RGBA8888)
    state._pending_texture_uploads.append(
        (widget.texture_ids[slot_index], converted_img.copy(), slot_index)
    )
    widget.update()

def upload_source_pil_image(widget, pil_image, slot_index: int):
    source_texture_ids = widget._source_texture_ids
    if slot_index not in (0, 1) or pil_image is None:
        return

    texture_id = source_texture_ids[slot_index] if slot_index < len(source_texture_ids) else 0
    if not texture_id:
        return

    queue_texture_upload(widget, pil_image, texture_id)

def upload_diff_source_pil_image(widget, pil_image):
    state = widget.runtime_state
    if pil_image is None or not widget._diff_source_texture_id:
        state._diff_source_pil_image = None
        state._diff_source_image_id = 0
        state._diff_source_ready = False
        return

    image_id = id(pil_image)
    if state._diff_source_ready and state._diff_source_image_id == image_id:
        return

    queue_texture_upload(widget, pil_image, widget._diff_source_texture_id)
    state._diff_source_pil_image = pil_image
    state._diff_source_image_id = image_id
    state._diff_source_ready = True

def letterbox_pil(widget, img: PilImage.Image, slot_index: int = -1) -> PilImage.Image:
    state = widget.runtime_state
    cw, ch = widget.width(), widget.height()
    if cw <= 0 or ch <= 0:
        if slot_index >= 0:
            state._letterbox_params[slot_index] = (0.0, 0.0, 1.0, 1.0)
        return img.convert("RGBA")

    img = img.convert("RGBA")
    ratio = min(cw / img.width, ch / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    offset_x = (cw - nw) // 2
    offset_y = (ch - nh) // 2
    if slot_index >= 0:

        state._letterbox_params[slot_index] = (
            offset_x / float(cw),
            offset_y / float(ch),
            nw / float(cw),
            nh / float(ch),
        )
        if slot_index == 0:
            state._content_rect_px = (offset_x, offset_y, nw, nh)
            state._clip_overlays_to_content_rect = False
    scaled = img.resize((nw, nh), PilImage.Resampling.BILINEAR)
    result = PilImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
    result.paste(scaled, (offset_x, offset_y))
    return result

def update_letterbox_geometry(widget, img: PilImage.Image | None, slot_index: int = -1):
    state = widget.runtime_state
    cw, ch = widget.width(), widget.height()
    if img is None or cw <= 0 or ch <= 0 or img.width <= 0 or img.height <= 0:
        if slot_index >= 0:
            state._letterbox_params[slot_index] = (0.0, 0.0, 1.0, 1.0)
            if slot_index == 0:
                state._content_rect_px = (0, 0, max(1, cw), max(1, ch))
                state._clip_overlays_to_content_rect = False
        return

    ratio = min(cw / img.width, ch / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    offset_x = (cw - nw) // 2
    offset_y = (ch - nh) // 2
    if slot_index >= 0:

        state._letterbox_params[slot_index] = (
            offset_x / float(cw),
            offset_y / float(ch),
            nw / float(cw),
            nh / float(ch),
        )
        if slot_index == 0:
            state._content_rect_px = (offset_x, offset_y, nw, nh)
            state._clip_overlays_to_content_rect = False


def update_common_letterbox_geometry(
    widget,
    image1: PilImage.Image | None,
    image2: PilImage.Image | None,
) -> None:
    """Keep both comparison sides in one canvas coordinate system."""
    reference = image1 if image1 is not None else image2
    update_letterbox_geometry(widget, reference, slot_index=0)
    while len(widget.runtime_state._letterbox_params) < 2:
        widget.runtime_state._letterbox_params.append(
            tuple(widget.runtime_state._letterbox_params[0])
        )
    widget.runtime_state._letterbox_params[1] = tuple(
        widget.runtime_state._letterbox_params[0]
    )


def upload_pil_images(
    widget,
    pil_image1,
    pil_image2,
    source_image1=None,
    source_image2=None,
    source_key=None,
    display_cache_key=None,
    shader_letterbox: bool = False,
):
    state = widget.runtime_state
    stored_ids = (
        display_cache_key
        if display_cache_key is not None
        else (
            id(pil_image1) if pil_image1 is not None else 0,
            id(pil_image2) if pil_image2 is not None else 0,
            pil_image1.size if pil_image1 is not None else None,
            pil_image2.size if pil_image2 is not None else None,
            bool(shader_letterbox),
        )
    )
    stored_changed = stored_ids != state._stored_image_ids
    state._stored_pil_images = [pil_image1, pil_image2]
    state._stored_image_ids = stored_ids
    state._shader_letterbox_mode = bool(shader_letterbox)
    has_explicit_source = source_image1 is not None and source_image2 is not None
    if has_explicit_source:
        explicit_source_sig = (
            id(source_image1) if source_image1 is not None else 0,
            id(source_image2) if source_image2 is not None else 0,
            source_image1.size if source_image1 is not None else None,
            source_image2.size if source_image2 is not None else None,
        )
        source_ids = (
            (source_key, explicit_source_sig)
            if source_key is not None
            else explicit_source_sig
        )
        source_changed = source_ids != state._source_image_ids
        state._source_pil_images = [source_image1, source_image2]
        state._source_image_ids = source_ids
        if source_changed:
            state._source_images_ready = False
    else:
        source_changed = state._source_image_ids is not None
        state._source_pil_images = [None, None]
        state._source_image_ids = None
        state._source_images_ready = False
    if pil_image1 and stored_changed:
        if state._shader_letterbox_mode:
            update_common_letterbox_geometry(widget, pil_image1, pil_image2)
            queue_texture_upload(widget, pil_image1, widget.texture_ids[0], slot_index=0)
        else:
            lb1 = letterbox_pil(widget, pil_image1, slot_index=0)
            queue_texture_upload(widget, lb1, widget.texture_ids[0], slot_index=0)
    if pil_image2 and stored_changed:
        if state._shader_letterbox_mode:
            update_common_letterbox_geometry(widget, pil_image1, pil_image2)
            queue_texture_upload(widget, pil_image2, widget.texture_ids[1], slot_index=1)
        else:
            lb2 = letterbox_pil(widget, pil_image2, slot_index=1)
            queue_texture_upload(widget, lb2, widget.texture_ids[1], slot_index=1)
    if has_explicit_source:
        try:
            if source_changed or not state._source_images_ready:
                if source_image1 is not None:
                    upload_source_pil_image(widget, source_image1, 0)
                if source_image2 is not None:
                    upload_source_pil_image(widget, source_image2, 1)
                state._source_images_ready = True
        except Exception:
            state._source_images_ready = False
            if hasattr(widget, "_schedule_source_preload"):
                widget._schedule_source_preload()
    widget.update()

def configure_offscreen_render(
    widget,
    *,
    stored_images,
    source_images,
    content_rect: tuple[int, int, int, int],
    shader_letterbox: bool = False,
):
    state = widget.runtime_state
    prev_stored_images = tuple(state._stored_pil_images)
    prev_source_images = tuple(state._source_pil_images)
    prev_content_rect = state._content_rect_px
    prev_shader_letterbox = state._shader_letterbox_mode
    images_unchanged = (
        prev_stored_images[0] is stored_images[0]
        and prev_stored_images[1] is stored_images[1]
        and prev_source_images[0] is source_images[0]
        and prev_source_images[1] is source_images[1]
    )
    state._store = None
    state._shader_letterbox_mode = bool(shader_letterbox)
    state._letterbox_params[0] = (0.0, 0.0, 1.0, 1.0)
    state._letterbox_params[1] = (0.0, 0.0, 1.0, 1.0)
    state._content_rect_px = content_rect
    state._clip_overlays_to_content_rect = False
    state._stored_pil_images = [stored_images[0], stored_images[1]]
    state._source_pil_images = [source_images[0], source_images[1]]
    state._source_images_ready = bool(source_images[0] is not None and source_images[1] is not None)

    if (
        images_unchanged
        and prev_content_rect == content_rect
        and prev_shader_letterbox == bool(shader_letterbox)
    ):
        return

    queue_texture_upload(widget, stored_images[0], widget.texture_ids[0], slot_index=0)
    queue_texture_upload(widget, stored_images[1], widget.texture_ids[1], slot_index=1)

    if source_images[0] is not None:
        queue_texture_upload(widget, source_images[0], widget._source_texture_ids[0])
    if source_images[1] is not None:
        queue_texture_upload(widget, source_images[1], widget._source_texture_ids[1])

def get_letterbox_params(widget, slot: int = 0) -> tuple:
    state = widget.runtime_state
    if slot < len(state._letterbox_params) and state._letterbox_params[slot]:
        return state._letterbox_params[slot]
    img = state._stored_pil_images[slot] if slot < len(state._stored_pil_images) else None
    w, h = widget.width(), widget.height()
    if img and w > 0 and h > 0:
        ratio = min(w / img.width, h / img.height)
        nw = max(1, int(img.width * ratio))
        nh = max(1, int(img.height * ratio))
        return ((w - nw) / (2.0 * w), (h - nh) / (2.0 * h), nw / float(w), nh / float(h))
    return (0.0, 0.0, 1.0, 1.0)

def clear_diff_texture(widget):
    state = widget.runtime_state
    state._diff_source_pil_image = None
    state._diff_source_image_id = 0
    state._diff_source_ready = False
