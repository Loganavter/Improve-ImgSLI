from __future__ import annotations

from PIL import Image

from core.store import Store
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.canvas.registry import registry
from ui.canvas_presentation.models import PresentationImageSet, SnapshotStorePresentation


def _get_unified_images(
    image1,
    image2,
    fit_content,
    global_bounds,
    fill_color=None,
    *,
    resize_method: str = "LANCZOS",
):
    from shared.image_processing.pixel_ops.unify import unify_pair
    from shared.image_processing.tiled_pixel_store import (
        TiledPixelStore,
        maybe_wrap_pixel_store,
    )

    if image1 is not None and image2 is not None:
        return unify_pair(image1, image2, resize_method)

    def _as_rgba_source(image):
        if image is None:
            return None
        if isinstance(image, TiledPixelStore):
            return image
        if isinstance(image, Image.Image):
            rgba = image if image.mode == "RGBA" else image.convert("RGBA")
            return maybe_wrap_pixel_store(rgba)
        return image

    return _as_rgba_source(image1), _as_rgba_source(image2)

def _build_snapshot_store(
    snap,
    image1,
    image2,
    *,
    fit_content: bool = False,
    global_bounds=None,
    fill_color=None,
    resize_method: str = "LANCZOS",
    normalize_snapshot: bool = True,
):
    store = Store()
    # `resolve_feature_virtual_layout` (called further below via
    # `build_render_frame_presentation`) looks up the canvas feature registry
    # keyed by the active session's `session_type`; the default session
    # `Store()` creates is "session_picker", which has no registered
    # features, so it must be switched to an "image_compare" session before
    # any layout-dependent feature (e.g. magnifier) can be resolved.
    store.create_workspace_session(session_type="image_compare", activate=True)
    store.set_session_state_slot("document", DocumentModel())
    store.viewport = snap.viewport_state.clone()
    store.settings = snap.settings_state.freeze_for_export()
    store.runtime_cache.overlay_clip_rect = None
    normalize_snapshot_command = registry().get_feature_command_by_alias("overlay.snapshot_normalize")
    should_normalize_snapshot = normalize_snapshot and not (
        fit_content and global_bounds is not None
    )
    if normalize_snapshot_command is not None and should_normalize_snapshot:
        normalize_snapshot_command(store)

    source_img1, source_img2 = _get_unified_images(
        image1,
        image2,
        fit_content,
        global_bounds,
        fill_color,
        resize_method=resize_method,
    )
    display_img1, display_img2 = source_img1, source_img2

    if fit_content and global_bounds:
        pad_left = int(global_bounds.pad_left)
        pad_right = int(global_bounds.pad_right)
        pad_top = int(global_bounds.pad_top)
        pad_bottom = int(global_bounds.pad_bottom)
        base_w = int(global_bounds.base_width)
        base_h = int(global_bounds.base_height)
        virtual_w = base_w + pad_left + pad_right
        virtual_h = base_h + pad_top + pad_bottom
        content_offset_x, content_offset_y = 0, 0
        content_w, content_h = base_w, base_h
        if virtual_w > 0 and virtual_h > 0 and base_w > 0 and base_h > 0:
            from shared.image_processing.pixel_ops.resample import (
                write_resampled_to_store,
            )
            from shared.image_processing.tiled_pixel_store import TiledPixelStore

            fitted1, fitted2 = source_img1, source_img2
            img_w = fitted1.width if fitted1 else 0
            img_h = fitted1.height if fitted1 else 0
            if img_w > base_w or img_h > base_h:
                fit_r = min(base_w / max(1, img_w), base_h / max(1, img_h))
                new_w = max(1, int(img_w * fit_r))
                new_h = max(1, int(img_h * fit_r))
                resample = Image.Resampling.LANCZOS
                if fitted1 is not None:
                    out1 = TiledPixelStore.allocate(new_w, new_h)
                    write_resampled_to_store(out1, fitted1, new_w, new_h, resample)
                    fitted1 = out1
                if fitted2 is not None:
                    out2 = TiledPixelStore.allocate(new_w, new_h)
                    write_resampled_to_store(out2, fitted2, new_w, new_h, resample)
                    fitted2 = out2
                img_w, img_h = new_w, new_h
            # Keep display unpadded; pads live in virtual layout / plan geometry.
            display_img1 = fitted1
            display_img2 = fitted2
            content_offset_x = (base_w - img_w) // 2
            content_offset_y = (base_h - img_h) // 2
            content_w, content_h = img_w, img_h
        apply_virtual_layout = registry().get_feature_command_by_alias(
            "overlay.snapshot_apply_virtual_layout"
        )
        if apply_virtual_layout is not None:
            apply_virtual_layout(
                store,
                base_w=base_w,
                base_h=base_h,
                virtual_layout=global_bounds.to_virtual_layout(),
                content_offset_x=content_offset_x,
                content_offset_y=content_offset_y,
                content_w=content_w,
                content_h=content_h,
            )
    store.viewport.session_data.image_state.image1 = display_img1
    store.viewport.session_data.image_state.image2 = display_img2
    document = store.get_session_state_slot("document")
    document.image1_path = getattr(snap, "image1_path", None)
    document.image2_path = getattr(snap, "image2_path", None)
    document.image_list1 = [
        ImageItem(
            image=source_img1,
            path=getattr(snap, "image1_path", None) or "",
            display_name=getattr(snap, "name1", None) or "",
        )
    ]
    document.image_list2 = [
        ImageItem(
            image=source_img2,
            path=getattr(snap, "image2_path", None) or "",
            display_name=getattr(snap, "name2", None) or "",
        )
    ]
    document.current_index1 = 0 if document.image_list1 else -1
    document.current_index2 = 0 if document.image_list2 else -1
    document.original_image1 = source_img1
    document.original_image2 = source_img2
    document.full_res_image1 = source_img1
    document.full_res_image2 = source_img2
    store.viewport.interaction_state.is_interactive_mode = False

    source_key = (
        getattr(snap, "image1_path", None),
        getattr(snap, "image2_path", None),
        source_img1.size if source_img1 is not None else None,
        source_img2.size if source_img2 is not None else None,
        fit_content,
        fill_color or (0, 0, 0, 0),
    )
    global_bounds_key = None
    if global_bounds is not None:
        global_bounds_key = (
            int(getattr(global_bounds, "pad_left", 0) or 0),
            int(getattr(global_bounds, "pad_right", 0) or 0),
            int(getattr(global_bounds, "pad_top", 0) or 0),
            int(getattr(global_bounds, "pad_bottom", 0) or 0),
            int(getattr(global_bounds, "base_width", 0) or 0),
            int(getattr(global_bounds, "base_height", 0) or 0),
            float(getattr(global_bounds, "canvas_x_min", 0.0) or 0.0),
            float(getattr(global_bounds, "canvas_x_max", 0.0) or 0.0),
            float(getattr(global_bounds, "canvas_y_min", 0.0) or 0.0),
            float(getattr(global_bounds, "canvas_y_max", 0.0) or 0.0),
        )
    display_cache_key = (
        getattr(snap, "image1_path", None),
        getattr(snap, "image2_path", None),
        display_img1.size if display_img1 is not None else None,
        display_img2.size if display_img2 is not None else None,
        source_img1.size if source_img1 is not None else None,
        source_img2.size if source_img2 is not None else None,
        fit_content,
        fill_color or (0, 0, 0, 0),
        global_bounds_key,
    )
    return store, display_img1, display_img2, source_img1, source_img2, source_key, display_cache_key

def build_snapshot_store_presentation(
    snap,
    image1,
    image2,
    *,
    fit_content: bool = False,
    global_bounds=None,
    fill_color=None,
    resize_method: str = "LANCZOS",
    normalize_snapshot: bool = True,
) -> SnapshotStorePresentation:
    (
        store,
        display_img1,
        display_img2,
        source_img1,
        source_img2,
        source_key,
        display_cache_key,
    ) = _build_snapshot_store(
        snap,
        image1,
        image2,
        fit_content=fit_content,
        global_bounds=global_bounds,
        fill_color=fill_color,
        resize_method=resize_method,
        normalize_snapshot=normalize_snapshot,
    )
    return SnapshotStorePresentation(
        store=store,
        images=PresentationImageSet(
            display_image1=display_img1,
            display_image2=display_img2,
            source_image1=source_img1,
            source_image2=source_img2,
            source_key=source_key,
            display_cache_key=display_cache_key,
        ),
        fit_content=fit_content,
        fill_rgba=fill_color or (0, 0, 0, 0),
        virtual_layout=(global_bounds.to_virtual_layout() if global_bounds is not None else None),
    )

