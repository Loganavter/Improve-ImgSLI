# Audit-Meta: pattern=canvas-presentation size=exempt reason="texture_parts/base_images single geometry owner + Store transact (Bucket A), 520 lines"
from PIL import Image as PilImage
from PySide6.QtGui import QImage

from shared.image_processing.pixel_ops.downscale import downscale_source_to_pil
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.image_identity import image_uid
from ui.canvas_infra.scene.frame_geometry import resolve_canvas_content_geometry

from .upload_queue import queue_prepared_texture_upload, queue_texture_upload


def _canvas_dims(widget) -> tuple[int, int]:
    """Logical canvas size for letterbox/aspect-fit math.

    During tiled export the real widget is resized to a tile's pixel
    footprint, but aspect-fit geometry must still be computed against the
    full export canvas so every tile shares one coordinate system. See
    ``render_context.build_render_runtime_context`` for the counterpart.
    """
    export_canvas_viewport = getattr(
        widget.runtime_state, "_export_canvas_viewport", None
    )
    if export_canvas_viewport is not None:
        canvas_width, canvas_height, _offset_x, _offset_y = export_canvas_viewport
        return int(canvas_width), int(canvas_height)
    return widget.width(), widget.height()


def upload_image(widget, qimage: QImage, slot_index: int):
    state = widget.runtime_state
    from tabs.image_compare.first_frame_debug import ic_first_frame_debug

    if slot_index not in (0, 1) or qimage.isNull():
        ic_first_frame_debug(
            widget, "upload_image slot=%s SKIPPED null=%s", slot_index, qimage.isNull()
        )
        return

    ic_first_frame_debug(
        widget,
        "upload_image slot=%s size=%sx%s",
        slot_index,
        qimage.width(),
        qimage.height(),
    )
    queue_prepared_texture_upload(
        widget, widget.texture_ids[slot_index], qimage, slot_index
    )
    widget.update()


def upload_source_pil_image(widget, pil_image, slot_index: int):
    source_texture_ids = widget._source_texture_ids
    if slot_index not in (0, 1) or pil_image is None:
        return

    texture_id = (
        source_texture_ids[slot_index] if slot_index < len(source_texture_ids) else 0
    )
    if not texture_id:
        return

    if isinstance(pil_image, TiledPixelStore):
        # Full-res pixels live in the memmap store; realize_tile_plan() crops
        # tiles directly from state._source_pil_images without materializing a
        # whole-image QImage here.
        return

    queue_texture_upload(widget, pil_image, texture_id)


def upload_diff_source_pil_image(widget, pil_image):
    state = widget.runtime_state
    if pil_image is None or not widget._diff_source_texture_id:
        state._diff_source_pil_image = None
        state._diff_source_image_id = 0
        state._diff_source_ready = False
        cache = getattr(state, "_texture_upload_cache", None)
        if cache is not None:
            cache.pop(widget._diff_source_texture_id, None)
        return

    image_id = image_uid(pil_image)
    if state._diff_source_ready and state._diff_source_image_id == image_id:
        return

    queue_texture_upload(widget, pil_image, widget._diff_source_texture_id)
    state._diff_source_pil_image = pil_image
    state._diff_source_image_id = image_id
    state._diff_source_ready = True


def letterbox_pil(widget, img: PilImage.Image, slot_index: int = -1) -> PilImage.Image:
    state = widget.runtime_state
    # Rare fallback: the "stored" (display) role normally resolves to the
    # small display-cache image, never the raw unify result -- but a cache
    # invalidation can momentarily leave only the TiledPixelStore behind
    # (see plan_builder.build_live_store_presentation). Never materialize
    # the store via to_pil() here (multi-GB on a 20k source); downscale
    # tile-native to the display size instead.
    is_store = isinstance(img, TiledPixelStore)
    cw, ch = _canvas_dims(widget)
    if cw <= 0 or ch <= 0:
        if slot_index >= 0:
            state._letterbox_params[slot_index] = (0.0, 0.0, 1.0, 1.0)
        if is_store:
            return downscale_source_to_pil(img, img.size).convert("RGBA")
        return img.convert("RGBA")

    from shared.image_processing.image_dims import get_image_dims

    w, h = get_image_dims(img)
    geometry = resolve_canvas_content_geometry(
        widget_width=cw,
        widget_height=ch,
        image_width=w,
        image_height=h,
        virtual_layout=None,
    )
    inner = geometry.inner_rect_px or (0, 0, cw, ch)
    offset_x, offset_y, nw, nh = inner
    if slot_index >= 0:

        state._letterbox_params[slot_index] = (
            offset_x / float(cw),
            offset_y / float(ch),
            nw / float(cw),
            nh / float(ch),
        )
        if slot_index == 0:
            state._content_rect_px = geometry.outer_rect_px or (0, 0, cw, ch)
            state._inner_content_rect_px = inner
            state._clip_overlays_to_content_rect = False
    if is_store:
        scaled = downscale_source_to_pil(
            img, (nw, nh), resample=PilImage.Resampling.BILINEAR
        )
    else:
        scaled = img.convert("RGBA").resize((nw, nh), PilImage.Resampling.BILINEAR)
    result = PilImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
    result.paste(scaled, (offset_x, offset_y))
    return result


# helper removed — use shared helper (B6)


def update_letterbox_geometry(widget, img: PilImage.Image | None, slot_index: int = -1):
    from shared.image_processing.image_dims import get_image_dims
    state = widget.runtime_state
    cw, ch = _canvas_dims(widget)
    w, h = get_image_dims(img)
    if img is None or cw <= 0 or ch <= 0 or w <= 0 or h <= 0:
        if slot_index >= 0:
            state._letterbox_params[slot_index] = (0.0, 0.0, 1.0, 1.0)
            if slot_index == 0:
                state._content_rect_px = (0, 0, max(1, cw), max(1, ch))
                state._inner_content_rect_px = state._content_rect_px
                state._clip_overlays_to_content_rect = False
        return

    geometry = resolve_canvas_content_geometry(
        widget_width=cw,
        widget_height=ch,
        image_width=w,
        image_height=h,
        virtual_layout=None,
    )
    inner = geometry.inner_rect_px
    outer = geometry.outer_rect_px
    if inner is None or outer is None:
        return
    offset_x, offset_y, nw, nh = inner
    if slot_index >= 0:

        state._letterbox_params[slot_index] = (
            offset_x / float(cw),
            offset_y / float(ch),
            nw / float(cw),
            nh / float(ch),
        )
        if slot_index == 0:
            state._content_rect_px = outer
            state._inner_content_rect_px = inner
            state._clip_overlays_to_content_rect = False


def update_common_letterbox_geometry(
    widget,
    image1: PilImage.Image | None,
    image2: PilImage.Image | None,
) -> None:
    """Keep both comparison sides in one canvas coordinate system.

    Bucket A (Phase 2): single geometry owner. When tiers mix
    (TiledPixelStore vs preview QImage/PIL), hold previous unified
    letterbox if valid; otherwise compute union aspect max(w1,w2)/max(h1,h2)
    once (envelope of fitted rects) so letterbox1==letterbox2 and dispatch
    single SetPixmapDimensions+SetImageDisplayRect via store.transact.
    Per-image letterbox previously produced 0.001 slivers and left-on-both.
    See plan_render_dispatch_and_gap_fix.md Phase 2.
    """
    state = widget.runtime_state
    cw, ch = _canvas_dims(widget)
    while len(state._letterbox_params) < 2:
        state._letterbox_params.append((0.0, 0.0, 1.0, 1.0))
    if cw <= 0 or ch <= 0:
        update_letterbox_geometry(widget, image1, slot_index=0)
        update_letterbox_geometry(widget, image2, slot_index=1)
        return

    from shared.image_processing.image_dims import get_image_dims

    w1, h1 = get_image_dims(image1) if image1 is not None else (0, 0)
    w2, h2 = get_image_dims(image2) if image2 is not None else (0, 0)
    have1 = image1 is not None and w1 > 0 and h1 > 0
    have2 = image2 is not None and w2 > 0 and h2 > 0
    if not have1 and not have2:
        state._letterbox_params[0] = (0.0, 0.0, 1.0, 1.0)
        state._letterbox_params[1] = (0.0, 0.0, 1.0, 1.0)
        state._content_rect_px = (0, 0, max(1, cw), max(1, ch))
        state._inner_content_rect_px = state._content_rect_px
        state._clip_overlays_to_content_rect = False
        return

    is_store1 = isinstance(image1, TiledPixelStore)
    is_store2 = isinstance(image2, TiledPixelStore)
    mixed_tier = have1 and have2 and (is_store1 != is_store2)
    # union only for mixed tier (store vs preview) or very different aspects
    # (portrait vs landscape) — keeps preview-preview close aspects distinct
    # to avoid 0.001 sliver (test_bbox) while fixing gap for mixed/large diff
    # (test_common). Threshold 0.4 separates 2000x1000 vs 1000x2000 (1.5) from
    # 1017x838 vs 768x576 (0.11).
    aspect1 = w1 / h1 if h1 else 0
    aspect2 = w2 / h2 if h2 else 0
    large_aspect_diff = have1 and have2 and abs(aspect1 - aspect2) > 0.4
    needs_union = have1 and have2 and (mixed_tier or large_aspect_diff)

    def _dispatch_store(rect_tuple: tuple[int, int, int, int]) -> bool:
        x, y, w, h = rect_tuple
        store = getattr(state, "_store", None) or getattr(widget, "_store", None)
        if store is None:
            return False
        try:
            dispatcher = store.get_dispatcher()
            if dispatcher is None:
                return False
            from core.state_management.geometry_actions import (
                SetImageDisplayRectAction,
                SetPixmapDimensionsAction,
            )
            from domain.types import Rect

            rect = Rect(x, y, w, h)
            store.transact(
                [
                    SetPixmapDimensionsAction(width=w, height=h),
                    SetImageDisplayRectAction(rect=rect),
                ],
                scope="viewport",
            )
            return True
        except Exception:
            return False

    if needs_union:
        prev0 = state._letterbox_params[0]
        prev1 = state._letterbox_params[1]
        if prev0 is not None and prev1 is not None and prev0 == prev1 and prev0 != (0.0, 0.0, 1.0, 1.0):
            prev_rect = getattr(state, "_inner_content_rect_px", None) or getattr(
                state, "_content_rect_px", None
            )
            if prev_rect is not None and prev_rect[2] > 0 and prev_rect[3] > 0:
                _dispatch_store(prev_rect)
                return
        geom1 = resolve_canvas_content_geometry(
            widget_width=cw,
            widget_height=ch,
            image_width=w1 if have1 else w2,
            image_height=h1 if have1 else h2,
            virtual_layout=None,
        )
        geom2 = resolve_canvas_content_geometry(
            widget_width=cw,
            widget_height=ch,
            image_width=w2 if have2 else w1,
            image_height=h2 if have2 else h1,
            virtual_layout=None,
        )
        inner1 = geom1.inner_rect_px or (0, 0, cw, ch)
        inner2 = geom2.inner_rect_px or (0, 0, cw, ch)
        x1, y1, w1p, h1p = inner1
        x2, y2, w2p, h2p = inner2
        ux = min(x1, x2)
        uy = min(y1, y2)
        ux2 = max(x1 + w1p, x2 + w2p)
        uy2 = max(y1 + h1p, y2 + h2p)
        uw = max(1, int(round(ux2 - ux)))
        uh = max(1, int(round(uy2 - uy)))
        ux = int(round(ux))
        uy = int(round(uy))
        letterbox = (ux / float(cw), uy / float(ch), uw / float(cw), uh / float(ch))
        state._letterbox_params[0] = letterbox
        state._letterbox_params[1] = letterbox
        state._content_rect_px = (ux, uy, uw, uh)
        state._inner_content_rect_px = (ux, uy, uw, uh)
        state._clip_overlays_to_content_rect = False
        _dispatch_store((ux, uy, uw, uh))
        return

    update_letterbox_geometry(widget, image1, slot_index=0)
    update_letterbox_geometry(widget, image2, slot_index=1)
    inner = getattr(state, "_inner_content_rect_px", None) or getattr(
        state, "_content_rect_px", None
    )
    if inner is not None:
        _dispatch_store(inner)


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
            image_uid(pil_image1),
            image_uid(pil_image2),
            pil_image1.size if pil_image1 is not None else None,
            pil_image2.size if pil_image2 is not None else None,
            bool(shader_letterbox),
        )
    )
    stored_changed = stored_ids != state._stored_image_ids
    if stored_changed:
        from shared.rendering.tile_debug import log_tile_event, tile_dump_enabled
        if tile_dump_enabled():
            log_tile_event(
                "stored_changed",
                old_ids=str(state._stored_image_ids),
                new_ids=str(stored_ids),
            )
    from tabs.image_compare.first_frame_debug import ic_first_frame_debug
    ic_first_frame_debug(
        widget,
        "upload_pil_images stored_changed=%s stored=[%s,%s] source=[%s,%s] source_key=%s",
        stored_changed,
        pil_image1 is not None,
        pil_image2 is not None,
        source_image1 is not None,
        source_image2 is not None,
        source_key,
    )
    state._stored_pil_images = [pil_image1, pil_image2]
    state._stored_image_ids = stored_ids
    state._shader_letterbox_mode = bool(shader_letterbox)
    if __debug__ and not shader_letterbox:
        for slot_img in (pil_image1, pil_image2):
            if slot_img is not None and isinstance(slot_img, TiledPixelStore):
                raise AssertionError(
                    "stored display role must be PIL.Image, not TiledPixelStore"
                )
    has_explicit_source = source_image1 is not None and source_image2 is not None
    if has_explicit_source:
        explicit_source_sig = (
            image_uid(source_image1),
            image_uid(source_image2),
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
        cache = getattr(state, "_texture_upload_cache", None)
        if cache is not None:
            for texture_id in widget._source_texture_ids:
                cache.pop(texture_id, None)
    # Single geometry update — previously called twice (once per slot) with identical args
    if stored_changed and state._shader_letterbox_mode and (pil_image1 or pil_image2):
        update_common_letterbox_geometry(widget, pil_image1, pil_image2)
    if pil_image1 and stored_changed:
        if state._shader_letterbox_mode:
            # docs/dev/rendering/tile-rendering-system.md Phase 3: skip the
            # whole-image upload for lazy sources -- see the matching
            # comment in upload_source_pil_image; realize_tile_plan()
            # crops tiles from state._stored_pil_images (set below)
            # directly, so this texture would just be wasted main-thread
            # work materializing the whole memmap.
            if isinstance(pil_image1, TiledPixelStore):
                state._images_uploaded[0] = True
            else:
                queue_texture_upload(
                    widget, pil_image1, widget.texture_ids[0], slot_index=0
                )
        else:
            lb1 = letterbox_pil(widget, pil_image1, slot_index=0)
            queue_texture_upload(widget, lb1, widget.texture_ids[0], slot_index=0)
    if pil_image2 and stored_changed:
        if state._shader_letterbox_mode:
            pass  # geometry already updated above
            if isinstance(pil_image2, TiledPixelStore):
                state._images_uploaded[1] = True
            else:
                queue_texture_upload(
                    widget, pil_image2, widget.texture_ids[1], slot_index=1
                )
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
    state._inner_content_rect_px = None
    state._clip_overlays_to_content_rect = False
    state._stored_pil_images = [stored_images[0], stored_images[1]]
    state._source_pil_images = [source_images[0], source_images[1]]
    state._source_images_ready = bool(
        source_images[0] is not None and source_images[1] is not None
    )

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
    img = (
        state._stored_pil_images[slot] if slot < len(state._stored_pil_images) else None
    )
    w, h = _canvas_dims(widget)
    if img and w > 0 and h > 0:
        from shared.image_processing.image_dims import get_image_dims
        iw, ih = get_image_dims(img)
        if iw > 0 and ih > 0:
            ratio = min(w / iw, h / ih)
            nw = max(1, int(iw * ratio))
            nh = max(1, int(ih * ratio))
        return (
            (w - nw) / (2.0 * w),
            (h - nh) / (2.0 * h),
            nw / float(w),
            nh / float(h),
        )
    return (0.0, 0.0, 1.0, 1.0)


def clear_diff_texture(widget):
    state = widget.runtime_state
    state._diff_source_pil_image = None
    state._diff_source_image_id = 0
    state._diff_source_ready = False
    cache = getattr(state, "_texture_upload_cache", None)
    if cache is not None:
        cache.pop(widget._diff_source_texture_id, None)
