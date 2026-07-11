from __future__ import annotations

from dataclasses import replace

from shared.rendering import get_effective_export_interpolation_method
from shared.rendering.tab_canvas_services import build_render_scene
from ui.canvas_infra.scene.frame_geometry import resolve_canvas_clip_rect_px


def build_export_render_scene(
    store,
    divider_thickness_export: int,
    *,
    virtual_layout=None,
    image_w: int | None = None,
    image_h: int | None = None,
):
    scene = build_render_scene(
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
    clip_rect = resolve_canvas_clip_rect_px(
        virtual_layout,
        base_width=image_w,
        base_height=image_h,
    )
    return replace(scene, overlay_clip_rect=clip_rect)
