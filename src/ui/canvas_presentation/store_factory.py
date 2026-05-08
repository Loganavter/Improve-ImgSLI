from __future__ import annotations

from PIL import Image

from core.store import ImageItem, Store
from domain.types import Point

from .models import PresentationImageSet, SnapshotStorePresentation

def _clone_point(point):
    if point is None:
        return None
    return Point(point.x, point.y)

def _transform_point(point, pad_left, pad_top, base_w, base_h, virtual_w, virtual_h):
    if point is None or base_w <= 0 or base_h <= 0 or virtual_w <= 0 or virtual_h <= 0:
        return None
    return Point(
        (pad_left + point.x * base_w) / virtual_w,
        (pad_top + point.y * base_h) / virtual_h,
    )

def _normalize_capture_position(point, capture_size_relative: float) -> Point | None:
    if point is None:
        return None
    radius = max(0.0, float(capture_size_relative)) / 2.0
    min_pos = min(0.5, radius)
    max_pos = max(min_pos, 1.0 - radius)
    return Point(
        max(min_pos, min(max_pos, float(point.x))),
        max(min_pos, min(max_pos, float(point.y))),
    )

def _pad_image(img, width, height, left, top, fill_color=(0, 0, 0, 0)):
    padded = Image.new("RGBA", (width, height), fill_color)
    if img is not None:
        padded.alpha_composite(img.convert("RGBA"), (left, top))
    return padded

def _iter_mutable_magnifier_models(store):
    view = store.viewport.view_state
    raw_models = getattr(view, "magnifiers", None) or {}
    return [model for model in raw_models.values() if model is not None]

def _normalize_magnifier_models(store) -> None:
    for model in _iter_mutable_magnifier_models(store):
        capture_size = float(getattr(model, "capture_size_relative", 0.0) or 0.0)
        model.position = _normalize_capture_position(model.position, capture_size) or model.position
        model.frozen_position = _normalize_capture_position(model.frozen_position, capture_size)

_image_cache = {}
_IMAGE_CACHE_MAX = 32

def _get_unified_images(image1, image2, fit_content, global_bounds, fill_color=None):
    from shared.image_processing.resize import resize_images_processor

    path1 = id(image1) if image1 is not None else None
    path2 = id(image2) if image2 is not None else None
    size1 = image1.size if image1 is not None else None
    size2 = image2.size if image2 is not None else None
    resolved_fill = fill_color or (0, 0, 0, 0)
    cache_key = (path1, path2, size1, size2, fit_content, global_bounds, resolved_fill)

    cached = _image_cache.get(cache_key)
    if cached is not None:
        return cached

    img1 = image1.convert("RGBA") if image1 is not None else None
    img2 = image2.convert("RGBA") if image2 is not None else None

    if img1 is not None and img2 is not None:
        img1, img2 = resize_images_processor(img1, img2)

    if fit_content and global_bounds:
        pad_left, pad_right, pad_top, pad_bottom, base_w, base_h = global_bounds
        virtual_w = base_w + pad_left + pad_right
        virtual_h = base_h + pad_top + pad_bottom
        if virtual_w > 0 and virtual_h > 0 and base_w > 0 and base_h > 0:
            img1 = _pad_image(img1, virtual_w, virtual_h, pad_left, pad_top, resolved_fill)
            img2 = _pad_image(img2, virtual_w, virtual_h, pad_left, pad_top, resolved_fill)

    result = (img1, img2)
    if len(_image_cache) >= _IMAGE_CACHE_MAX:
        _image_cache.clear()
    _image_cache[cache_key] = result
    return result

def build_snapshot_store_presentation(
    snap,
    image1,
    image2,
    *,
    fit_content: bool = False,
    global_bounds=None,
    fill_color=None,
) -> SnapshotStorePresentation:
    store = Store()
    store.viewport = snap.viewport_state.clone()
    store.settings = snap.settings_state.freeze_for_export()
    store.viewport.divider_clip_rect = None
    _normalize_magnifier_models(store)

    source_img1, source_img2 = _get_unified_images(
        image1, image2, fit_content, global_bounds, fill_color
    )
    display_img1, display_img2 = source_img1, source_img2

    if fit_content and global_bounds:
        pad_left, pad_right, pad_top, pad_bottom, base_w, base_h = global_bounds
        virtual_w = base_w + pad_left + pad_right
        virtual_h = base_h + pad_top + pad_bottom

        if virtual_w > 0 and virtual_h > 0 and base_w > 0 and base_h > 0:
            view = store.viewport.view_state
            store.viewport.divider_clip_rect = (pad_left, pad_top, base_w, base_h)
            base_ref = float(max(base_w, base_h))
            virtual_ref = float(max(virtual_w, virtual_h))
            base_min = float(min(base_w, base_h))
            virtual_min = float(min(virtual_w, virtual_h))

            size_scale = (base_ref / virtual_ref) if virtual_ref > 0 else 1.0
            capture_scale = (base_min / virtual_min) if virtual_min > 0 else 1.0

            for model in _iter_mutable_magnifier_models(store):
                model.position = _transform_point(
                    _clone_point(model.position),
                    pad_left,
                    pad_top,
                    base_w,
                    base_h,
                    virtual_w,
                    virtual_h,
                ) or model.position
                model.frozen_position = _transform_point(
                    _clone_point(model.frozen_position),
                    pad_left,
                    pad_top,
                    base_w,
                    base_h,
                    virtual_w,
                    virtual_h,
                )
                model.capture_size_relative *= capture_scale
                model.size_relative *= size_scale
                model.spacing_relative *= size_scale
                model.offset_relative = Point(
                    model.offset_relative.x * size_scale,
                    model.offset_relative.y * size_scale,
                )

            if view.is_horizontal:
                view.split_position_visual = (
                    pad_top + view.split_position_visual * base_h
                ) / virtual_h
            else:
                view.split_position_visual = (
                    pad_left + view.split_position_visual * base_w
                ) / virtual_w

    store.viewport.session_data.image_state.image1 = display_img1
    store.viewport.session_data.image_state.image2 = display_img2
    store.document.image1_path = getattr(snap, "image1_path", None)
    store.document.image2_path = getattr(snap, "image2_path", None)
    store.document.image_list1 = [
        ImageItem(
            image=source_img1,
            path=getattr(snap, "image1_path", None) or "",
            display_name=getattr(snap, "name1", None) or "",
        )
    ]
    store.document.image_list2 = [
        ImageItem(
            image=source_img2,
            path=getattr(snap, "image2_path", None) or "",
            display_name=getattr(snap, "name2", None) or "",
        )
    ]
    store.document.current_index1 = 0 if store.document.image_list1 else -1
    store.document.current_index2 = 0 if store.document.image_list2 else -1
    store.document.original_image1 = source_img1
    store.document.original_image2 = source_img2
    store.document.full_res_image1 = display_img1 if fit_content else source_img1
    store.document.full_res_image2 = display_img2 if fit_content else source_img2
    store.viewport.interaction_state.is_interactive_mode = False

    source_key = (
        getattr(snap, "image1_path", None),
        getattr(snap, "image2_path", None),
        source_img1.size if source_img1 is not None else None,
        source_img2.size if source_img2 is not None else None,
        fit_content,
        fill_color or (0, 0, 0, 0),
    )

    return SnapshotStorePresentation(
        store=store,
        images=PresentationImageSet(
            display_image1=display_img1,
            display_image2=display_img2,
            source_image1=source_img1,
            source_image2=source_img2,
            source_key=source_key,
            display_cache_key=(
                id(display_img1) if display_img1 is not None else 0,
                id(display_img2) if display_img2 is not None else 0,
                display_img1.size if display_img1 is not None else None,
                display_img2.size if display_img2 is not None else None,
                fit_content,
            ),
        ),
        fit_content=fit_content,
        fill_rgba=fill_color or (0, 0, 0, 0),
    )
