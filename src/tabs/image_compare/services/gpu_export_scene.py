from __future__ import annotations

from dataclasses import replace

from shared.rendering import get_effective_export_interpolation_method
from shared.rendering.tab_canvas_services import build_gl_render_scene


def build_export_gl_scene(
    store,
    divider_thickness_export: int,
    *,
    virtual_layout=None,
    image_w: int | None = None,
    image_h: int | None = None,
):
    scene = build_gl_render_scene(
        store,
        apply_channel_mode_in_shader=True,
        clip_overlays_to_image_bounds=False,
    )
    old_overlay = scene.feature_overrides.get("filename_overlay")
    new_feature_overrides = {
        **scene.feature_overrides,
        "filename_divider_thickness": int(divider_thickness_export),
        **(
            {
                "filename_overlay": replace(
                    old_overlay,
                    divider_thickness=divider_thickness_export,
                )
            }
            if old_overlay is not None
            else {}
        ),
    }
    scene = replace(
        scene,
        feature_overrides=new_feature_overrides,
        zoom_interpolation_method=get_effective_export_interpolation_method(
            store.viewport
        ),
    )
    if virtual_layout is not None and image_w is not None and image_h is not None:
        scene = apply_virtual_canvas_layout_to_scene(
            scene,
            virtual_layout=virtual_layout,
            image_w=int(image_w),
            image_h=int(image_h),
        )
    return scene


def apply_virtual_canvas_layout_to_scene(
    scene,
    *,
    virtual_layout,
    image_w: int,
    image_h: int,
):
    canvas_bounds = virtual_layout.canvas_bounds
    content_bounds = virtual_layout.content_bounds
    canvas_width_units = max(float(canvas_bounds.width), 1e-6)
    canvas_height_units = max(float(canvas_bounds.height), 1e-6)

    if scene.is_horizontal:
        adjusted_split = (
            float(scene.split_position_visual) - float(canvas_bounds.y_min)
        ) / canvas_height_units
    else:
        adjusted_split = (
            float(scene.split_position_visual) - float(canvas_bounds.x_min)
        ) / canvas_width_units

    clip_x = int(
        round(
            (float(content_bounds.x_min) - float(canvas_bounds.x_min))
            * float(image_w)
        )
    )
    clip_y = int(
        round(
            (float(content_bounds.y_min) - float(canvas_bounds.y_min))
            * float(image_h)
        )
    )
    clip_w = max(1, int(round(float(content_bounds.width) * float(image_w))))
    clip_h = max(1, int(round(float(content_bounds.height) * float(image_h))))

    return replace(
        scene,
        split_position_visual=max(0.0, min(1.0, float(adjusted_split))),
        overlay_clip_rect=(clip_x, clip_y, clip_w, clip_h),
    )
