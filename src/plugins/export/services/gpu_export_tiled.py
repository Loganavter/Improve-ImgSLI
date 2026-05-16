from __future__ import annotations

import time
from dataclasses import replace

from PIL import Image
from PyQt6.QtGui import QColor

from shared.regions import build_square_tile_grid, pad_image_to_size
from ui.canvas_infra.scene.property_access import (
    read_canvas_feature_color_by_setting_key,
    read_canvas_feature_setting_by_key,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias
from ui.canvas_presentation.plan import CanvasRenderPlan
from ui.canvas_presentation.plan_builder import compute_canvas_plan

from .gpu_export_scene import (
    adjust_scene_split_for_tile,
    build_divider_export_overlay,
    build_export_gl_scene,
    qimage_to_pil,
    query_active_magnifier_divider_thickness,
    query_guides_state,
)

def render_tiled_image(
    *,
    widget,
    store,
    render_context,
    width: int,
    height: int,
    prepared_background_layers=None,
    min_tiles_per_axis: int = 2,
    stroke_scales: tuple[float, float, float] = (1.0, 1.0, 1.0),
    get_max_texture_size,
    render_widget_frame,
):
    from ui.canvas_presentation.plan_applicator import apply_render_plan_to_canvas

    if store.viewport.render_config.include_file_names_in_saved:
        raise RuntimeError("Tiled GPU export does not support filename overlay yet")

    max_tex = get_max_texture_size(widget)
    tile_grid = build_square_tile_grid(
        width,
        height,
        max_tile_extent=max_tex,
        min_tiles_per_axis=min_tiles_per_axis,
    )
    tile_debug = {
        "tile_columns": float(tile_grid.columns),
        "tile_rows": float(tile_grid.rows),
        "tile_width": float(tile_grid.tile_width),
        "tile_height": float(tile_grid.tile_height),
    }
    tile_w = tile_grid.tile_width
    tile_h = tile_grid.tile_height
    padded_w = tile_grid.padded_width
    padded_h = tile_grid.padded_height

    image1 = render_context.image1
    image2 = render_context.image2
    bg1, bg2 = prepared_background_layers or (image1, image2)
    bg1 = pad_image_to_size(bg1.convert("RGBA"), padded_w, padded_h)
    bg2 = pad_image_to_size(bg2.convert("RGBA"), padded_w, padded_h)
    src1 = pad_image_to_size(image1.convert("RGBA"), padded_w, padded_h)
    src2 = pad_image_to_size(image2.convert("RGBA"), padded_w, padded_h)
    diff_image = render_context.cached_diff_image
    if diff_image is not None:
        diff_image = pad_image_to_size(diff_image.convert("RGBA"), padded_w, padded_h)

    vp = store.viewport
    view = vp.view_state
    capture_visible = bool(read_canvas_feature_setting_by_key(vp, "capture.visible"))
    capture_color = read_canvas_feature_color_by_setting_key(vp, "capture.color")
    guides_state = query_guides_state(view)
    scale_x, scale_y, scale_ref = stroke_scales
    divider_overlay = build_divider_export_overlay(
        store,
        scale_x=scale_x,
        scale_y=scale_y,
        content_offset_x=0,
        content_offset_y=0,
        content_width=tile_w,
        content_height=tile_h,
    )
    divider_thickness_export = int(divider_overlay.get("thickness", 0))
    guides_thickness_export = int(guides_state.thickness)
    magnifier_divider_thickness_export = query_active_magnifier_divider_thickness(store)
    diff_mode = str(vp.view_state.diff_mode or "off")

    global_canvas_plan = compute_canvas_plan(
        store,
        width,
        height,
        overlay_drawing_coords=render_context.overlay_drawing_coords,
    )
    pad_left = global_canvas_plan.padding_left
    pad_top_offset = global_canvas_plan.padding_top

    build_overlay_layout = get_canvas_feature_command_by_alias(
        "overlay.render_build_layout"
    )
    overlay_enabled_query = get_canvas_feature_command_by_alias("overlay.enabled")
    global_layout = (
        build_overlay_layout(
            vp,
            width=width,
            height=height,
            canvas_width=padded_w,
            canvas_height=padded_h,
            content_offset_x=float(pad_left),
            content_offset_y=float(pad_top_offset),
            divider_thickness_px=magnifier_divider_thickness_export,
        )
        if (
            build_overlay_layout is not None
            and overlay_enabled_query is not None
            and overlay_enabled_query(store)
        )
        else None
    )
    base_gl_scene = build_export_gl_scene(store, divider_thickness_export)
    base_diff_int = global_layout.diff_mode if global_layout is not None else 0

    final_image = Image.new("RGBA", (padded_w, padded_h), (0, 0, 0, 0))
    resize_show_started = time.perf_counter()
    widget.resize(tile_w, tile_h)
    widget.show()
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()
    tile_debug["tile_resize_show_ms"] = (time.perf_counter() - resize_show_started) * 1000.0

    tile_paint_total = 0.0
    tile_grab_total = 0.0
    tile_paste_total = 0.0

    shift_layout_to_tile = get_canvas_feature_command_by_alias(
        "overlay.render_shift_layout_to_tile"
    )

    for _row, _col, tile_region in tile_grid.iter_regions():
        tile_left = tile_region.left
        tile_top = tile_region.top
        actual_w = tile_region.width
        actual_h = tile_region.height

        box = (tile_left, tile_top, tile_left + tile_w, tile_top + tile_h)
        tile_bg1 = bg1.crop(box)
        tile_bg2 = bg2.crop(box)
        tile_src1 = src1.crop(box)
        tile_src2 = src2.crop(box)
        tile_diff = diff_image.crop(box) if diff_image is not None else None

        if global_layout is not None:
            effective_diff_int = 4 if diff_mode == "ssim" and diff_image is not None else base_diff_int
            tile_layout = replace(
                shift_layout_to_tile(
                    global_layout,
                    tile_left=tile_left,
                    tile_top=tile_top,
                ) if shift_layout_to_tile is not None else global_layout,
                diff_mode=effective_diff_int,
            )
        else:
            tile_layout = None

        gl_scene = adjust_scene_split_for_tile(
            base_gl_scene,
            pad_left=pad_left,
            pad_top=pad_top_offset,
            image_w=width,
            image_h=height,
            tile_left=tile_left,
            tile_top=tile_top,
            tile_w=tile_w,
            tile_h=tile_h,
        )

        plan = CanvasRenderPlan(
            image1=tile_bg1,
            image2=tile_bg2,
            source_image1=tile_src1,
            source_image2=tile_src2,
            source_key=(),
            canvas_w=tile_w,
            canvas_h=tile_h,
            gl_scene=gl_scene,
            overlay_layout=tile_layout,
            capture_visible=capture_visible,
            capture_color=QColor(
                capture_color.r,
                capture_color.g,
                capture_color.b,
                capture_color.a,
            ),
            guides_enabled=bool(guides_state.enabled),
            guides_color=QColor(
                guides_state.color.r,
                guides_state.color.g,
                guides_state.color.b,
                guides_state.color.a,
            ),
            guides_thickness=guides_thickness_export,
            display_cache_key=None,
            output_scale=max(1.0, float(scale_ref)),
            preserve_zoom=False,
        )
        apply_render_plan_to_canvas(widget, plan)
        widget.upload_diff_source_pil_image(tile_diff)

        paint_started = time.perf_counter()
        render_widget_frame(widget)
        tile_paint_total += (time.perf_counter() - paint_started) * 1000.0

        grab_started = time.perf_counter()
        tile_img = qimage_to_pil(widget.grabFramebuffer())
        tile_grab_total += (time.perf_counter() - grab_started) * 1000.0

        paste_started = time.perf_counter()
        final_image.paste(tile_img.crop((0, 0, actual_w, actual_h)), (tile_left, tile_top))
        tile_paste_total += (time.perf_counter() - paste_started) * 1000.0

    tile_debug["tile_paint_ms"] = tile_paint_total
    tile_debug["tile_grab_ms"] = tile_grab_total
    tile_debug["tile_paste_ms"] = tile_paste_total
    return final_image.crop((0, 0, width, height)), tile_debug
