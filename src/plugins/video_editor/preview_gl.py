from types import SimpleNamespace

from PIL import Image

from core.store import ImageItem, Store
from domain.types import Point
from domain.types import Rect
from shared.image_processing.resize import resize_images_processor
from ui.presenters.image_canvas.magnifier import render_magnifier_gl_fast
from ui.presenters.image_canvas.signatures import get_divider_color_tuple
from ui.widgets.gl_canvas.scene import build_gl_render_scene
from ui.widgets.gl_canvas.helpers import reset_canvas_overlays

class _PreviewPresenterAdapter:
    def __init__(self, store, image_label):
        self.store = store
        self.ui = SimpleNamespace(image_label=image_label)
        self.view = SimpleNamespace(
            get_divider_color_tuple=self._get_divider_color_tuple,
            sync_widget_overlay_coords=lambda: None,
        )

    def get_current_label_dimensions(self):
        return self.ui.image_label.width(), self.ui.image_label.height()

    def _get_divider_color_tuple(self, vp):
        return get_divider_color_tuple(vp)

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

def _pad_image(img, width, height, left, top, fill_color=(0, 0, 0, 0)):
    padded = Image.new("RGBA", (width, height), fill_color)
    if img is not None:
        padded.alpha_composite(img.convert("RGBA"), (left, top))
    return padded

def _compute_display_size(canvas, image):
    if image is None:
        return 0, 0

    canvas_w = max(1, canvas.width())
    canvas_h = max(1, canvas.height())
    ratio = min(canvas_w / image.width, canvas_h / image.height)
    return max(1, int(image.width * ratio)), max(1, int(image.height * ratio))

_image_cache = {}
_IMAGE_CACHE_MAX = 32

def _get_unified_images(image1, image2, fit_content, global_bounds, fill_color=None):
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

def build_preview_store(
    snap,
    image1,
    image2,
    fit_content=False,
    global_bounds=None,
    fill_color=None,
):
    store = Store()
    store.viewport = snap.viewport_state.clone()
    store.settings = snap.settings_state.freeze_for_export()
    store.viewport.divider_clip_rect = None

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

            view.capture_position_relative = _transform_point(
                _clone_point(view.capture_position_relative),
                pad_left,
                pad_top,
                base_w,
                base_h,
                virtual_w,
                virtual_h,
            ) or view.capture_position_relative

            view.frozen_capture_point_relative = _transform_point(
                _clone_point(view.frozen_capture_point_relative),
                pad_left,
                pad_top,
                base_w,
                base_h,
                virtual_w,
                virtual_h,
            )

            view.capture_size_relative *= capture_scale
            view.magnifier_size_relative *= size_scale
            view.magnifier_spacing_relative *= size_scale
            view.magnifier_spacing_relative_visual *= size_scale
            view.magnifier_offset_relative = Point(
                view.magnifier_offset_relative.x * size_scale,
                view.magnifier_offset_relative.y * size_scale,
            )
            view.magnifier_offset_relative_visual = Point(
                view.magnifier_offset_relative_visual.x * size_scale,
                view.magnifier_offset_relative_visual.y * size_scale,
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

    return store, display_img1, display_img2, source_img1, source_img2, source_key

def _prepare_diff_layers(diff_mode, img1, img2):
    try:
        from plugins.analysis.processing import (
            create_edge_map,
            create_grayscale_diff,
            create_highlight_diff,
            create_ssim_map,
        )

        if diff_mode == "edges":
            return (
                create_edge_map(img1) or img1,
                create_edge_map(img2) or img2,
            )

        diff_builders = {
            "highlight": lambda: create_highlight_diff(img1, img2, threshold=10),
            "grayscale": lambda: create_grayscale_diff(img1, img2),
            "ssim": lambda: create_ssim_map(img1, img2),
        }
        diff_image = diff_builders.get(diff_mode, lambda: None)()
        if diff_image is not None:
            return diff_image, diff_image
    except Exception:
        logger.exception("Failed to prepare diff layers for preview")

    return img1, img2

def apply_preview_to_canvas(
    canvas,
    preview_store,
    image1,
    image2,
    fit_content=False,
    source_image1=None,
    source_image2=None,
    source_key=None,
):
    adapter = _PreviewPresenterAdapter(preview_store, canvas)

    if hasattr(canvas, "begin_update_batch"):
        canvas.begin_update_batch()

    try:
        canvas._store = preview_store
        canvas.set_render_scene(
            build_gl_render_scene(
                preview_store,
                apply_channel_mode_in_shader=getattr(
                    canvas, "_apply_channel_mode_in_shader", True
                ),
                clip_overlays_to_image_bounds=True,
            )
        )
        canvas.set_split_position_sync(
            lambda split: _sync_preview_split_position(preview_store, split)
        )
        canvas._clip_overlays_to_content_rect = not fit_content
        canvas.reset_view()
        display_w, display_h = _compute_display_size(canvas, image1)
        preview_store.viewport.geometry_state.pixmap_width = display_w
        preview_store.viewport.geometry_state.pixmap_height = display_h
        preview_store.viewport.geometry_state.image_display_rect_on_label = Rect(
            (canvas.width() - display_w) // 2,
            (canvas.height() - display_h) // 2,
            display_w,
            display_h,
        )
        diff_mode = getattr(preview_store.viewport.view_state, "diff_mode", "off")

        if diff_mode != "off":
            display_img1, display_img2 = _prepare_diff_layers(
                diff_mode, source_image1 or image1, source_image2 or image2
            )
            canvas.set_apply_channel_mode_in_shader(False)
        else:
            display_img1 = image1
            display_img2 = image2
            canvas.set_apply_channel_mode_in_shader(True)

        prev_key = getattr(canvas, "_preview_source_key", None)
        prev_fit = getattr(canvas, "_preview_fit_content", None)
        diff_key = (source_key, diff_mode) if diff_mode != "off" else source_key
        images_changed = diff_key != prev_key or fit_content != prev_fit
        canvas._preview_source_key = diff_key
        canvas._preview_fit_content = fit_content

        if images_changed:
            canvas.set_pil_layers(
                display_img1,
                display_img2,
                source_key=diff_key,
                shader_letterbox=True,
            )
        else:
            canvas.update()

        if preview_store.viewport.view_state.use_magnifier:
            render_magnifier_gl_fast(adapter)
        else:
            reset_canvas_overlays(canvas)
    finally:
        canvas.end_update_batch()

def _sync_preview_split_position(preview_store, split_position: float):
    viewport = preview_store.viewport
    viewport.view_state.split_position = split_position
    viewport.view_state.split_position_visual = split_position
