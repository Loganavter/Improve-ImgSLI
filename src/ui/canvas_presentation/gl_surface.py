from __future__ import annotations

from domain.types import Rect
from ui.canvas_features.magnifier import MagnifierModeService, iter_magnifier_models
from ui.canvas_infra.viewport.state import (
    get_pan_offset_x,
    get_pan_offset_y,
    get_zoom_level,
    set_pan_offsets,
    set_zoom_level,
)
from ui.presenters.image_canvas.magnifier_parts.gl_render import render_magnifier_gl_fast
from ui.presenters.image_canvas.signatures import get_divider_color_tuple
from ui.widgets.gl_canvas.helpers import reset_canvas_overlays
from ui.widgets.gl_canvas.scene import build_gl_render_scene

from .layout import compute_content_layout
from .live_store import build_live_store_presentation
from .models import CanvasTarget

class _StorePresenterAdapter:
    def __init__(self, store, canvas):
        self.store = store
        self.ui = _CanvasUI(canvas)
        self.view = _CanvasView()

    def get_current_label_dimensions(self):
        return self.ui.image_label.width(), self.ui.image_label.height()

class _CanvasUI:
    def __init__(self, canvas):
        self.image_label = canvas

class _CanvasView:
    def get_divider_color_tuple(self, vp):
        return get_divider_color_tuple(vp)

    def sync_widget_overlay_coords(self):
        return None

def _compute_display_size(canvas, image):
    if image is None:
        return 0, 0
    canvas_w = max(1, canvas.width())
    canvas_h = max(1, canvas.height())
    ratio = min(canvas_w / image.width, canvas_h / image.height)
    return max(1, int(image.width * ratio)), max(1, int(image.height * ratio))

def _sync_split_position(store, canvas, split_position: float):
    viewport = store.viewport
    viewport.view_state.split_position = split_position
    viewport.view_state.split_position_visual = split_position
    canvas.set_render_scene(
        build_gl_render_scene(
            store,
            apply_channel_mode_in_shader=getattr(
                canvas, "_apply_channel_mode_in_shader", True
            ),
            clip_overlays_to_image_bounds=getattr(
                canvas, "_clip_overlays_to_content_rect", False
            ),
        )
    )
    store.emit_viewport_change("interaction")

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
        import logging

        logging.getLogger("ImproveImgSLI").exception(
            "Failed to prepare diff layers for GL presentation"
        )

    return img1, img2

def apply_store_to_gl_canvas(
    canvas,
    store,
    image1,
    image2,
    *,
    fit_content: bool = False,
    source_image1=None,
    source_image2=None,
    source_key=None,
    display_cache_key=None,
    clip_overlays_to_image_bounds: bool = False,
    layers_are_prepared: bool = False,
):
    presentation = build_live_store_presentation(store)
    display_image1 = image1 or presentation.display_image1
    display_image2 = image2 or presentation.display_image2
    source_image1 = source_image1 or presentation.source_image1
    source_image2 = source_image2 or presentation.source_image2
    source_key = source_key or presentation.source_key
    display_cache_key = (
        display_cache_key
        if display_cache_key is not None
        else (None if layers_are_prepared else presentation.display_cache_key)
    )
    adapter = _StorePresenterAdapter(store, canvas)

    if hasattr(canvas, "begin_update_batch"):
        canvas.begin_update_batch()

    try:
        canvas._store = store
        canvas.set_render_scene(
            build_gl_render_scene(
                store,
                apply_channel_mode_in_shader=getattr(
                    canvas, "_apply_channel_mode_in_shader", True
                ),
                clip_overlays_to_image_bounds=clip_overlays_to_image_bounds,
            )
        )
        canvas.set_split_position_sync(
            lambda split: _sync_split_position(store, canvas, split)
        )
        canvas._clip_overlays_to_content_rect = clip_overlays_to_image_bounds and not fit_content
        preserve_view_transform = not fit_content
        if preserve_view_transform:
            zoom_level = get_zoom_level(canvas)
            pan_x = get_pan_offset_x(canvas)
            pan_y = get_pan_offset_y(canvas)
        canvas.reset_view()
        if preserve_view_transform:
            set_zoom_level(canvas, zoom_level)
            set_pan_offsets(canvas, pan_x, pan_y)

        layout = compute_content_layout(
            CanvasTarget(width=canvas.width(), height=canvas.height()),
            image_width=display_image1.width if display_image1 is not None else 0,
            image_height=display_image1.height if display_image1 is not None else 0,
        )
        display_w, display_h = layout.content_width, layout.content_height
        store.viewport.geometry_state.pixmap_width = display_w
        store.viewport.geometry_state.pixmap_height = display_h
        store.viewport.geometry_state.image_display_rect_on_label = Rect(
            layout.content_x,
            layout.content_y,
            display_w,
            display_h,
        )

        diff_mode = getattr(store.viewport.view_state, "diff_mode", "off")
        if diff_mode != "off" and not layers_are_prepared:
            display_img1, display_img2 = _prepare_diff_layers(
                diff_mode,
                source_image1 or display_image1,
                source_image2 or display_image2,
            )
            canvas.set_apply_channel_mode_in_shader(False)
        else:
            display_img1 = display_image1
            display_img2 = display_image2
            canvas.set_apply_channel_mode_in_shader(True)

        canvas.set_pil_layers(
            display_img1,
            display_img2,
            source_image1=source_image1,
            source_image2=source_image2,
            source_key=source_key,
            display_cache_key=display_cache_key,
            shader_letterbox=True,
        )

        mode_service = MagnifierModeService(store)
        visible_models = [
            model
            for model in iter_magnifier_models(
                store.viewport.view_state,
                store.viewport.render_config,
            )
            if bool(model.visible)
        ]
        if mode_service.should_render_magnifiers() and visible_models:
            render_magnifier_gl_fast(adapter)
        else:
            reset_canvas_overlays(canvas)
    finally:
        canvas.end_update_batch()
