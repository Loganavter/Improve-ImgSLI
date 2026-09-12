from __future__ import annotations

from PySide6.QtGui import QColor

from ui.canvas_infra.scene.frame_geometry import resolve_canvas_clip_rect_px
from ui.canvas_infra.scene.layout_requirements import resolve_feature_virtual_layout
from ui.canvas_infra.scene.property_access import (
    read_canvas_feature_color_by_setting_key,
    read_canvas_feature_setting_by_key,
)
from tabs.image_compare.canvas.registry import registry
from tabs.image_compare.canvas.scene import build_render_scene
from ui.canvas_presentation.plan import CanvasRenderPlan

from tabs.image_compare.canvas.presentation.geometry import (
    CanvasGeometry,
    _FallbackGuidesState,
    compute_canvas_plan,
)
from tabs.image_compare.canvas.presentation.live_presentation import (
    build_live_store_presentation,
)
from tabs.image_compare.canvas.presentation.snapshot_frame import (
    build_render_frame_presentation,
)
from tabs.image_compare.canvas.presentation.snapshot_store import (
    _build_snapshot_store,
    _get_unified_images,
    build_snapshot_store_presentation,
)

__all__ = [
    "CanvasGeometry",
    "build_canvas_plan",
    "build_live_store_presentation",
    "build_render_frame_presentation",
    "build_snapshot_store_presentation",
    "compute_canvas_plan",
    "_get_unified_images",
]

def build_canvas_plan(
    viewport_source,
    image1,
    image2,
    *,
    source_image1=None,
    source_image2=None,
    source_key=None,
    display_cache_key=None,
    target_size: tuple[int, int] | None = None,
    content_size: tuple[int, int] | None = None,
    output_scale: float = 1.0,
    fit_content: bool = False,
    preserve_zoom: bool = False,
    global_bounds=None,
    fill_color=None,
    pad_left: int = 0,
    pad_top: int = 0,
    render_scene=None,
    divider_thickness_px: int | None = None,
    guides_thickness: int | None = None,
    image_is_padded_composite: bool = False,
    geometry_letterbox: bool = False,
) -> CanvasRenderPlan:
    if hasattr(viewport_source, "viewport"):
        store = viewport_source
        vp = store.viewport
        display_image1 = image1
        display_image2 = image2
        source_image1 = source_image1 if source_image1 is not None else image1
        source_image2 = source_image2 if source_image2 is not None else image2
        source_key = source_key or ()
    else:
        store, display_image1, display_image2, source_image1, source_image2, source_key, display_cache_key = _build_snapshot_store(
            viewport_source,
            image1,
            image2,
            fit_content=fit_content,
            global_bounds=global_bounds,
            fill_color=fill_color,
        )
        vp = store.viewport
        # Padding is expressed via virtual layout / overlay_clip_rect, not by
        # baking pads into display pixels (see tile-rendering-system.md).
        image_is_padded_composite = bool(image_is_padded_composite)

    is_live_default_plan = (
        hasattr(viewport_source, "viewport")
        and target_size is None
        and render_scene is None
    )
    if is_live_default_plan and display_image1 is not None:
        live_virtual_layout = resolve_feature_virtual_layout(
            store,
            drawing_width=display_image1.width,
            drawing_height=display_image1.height,
        )
        live_pad_left, live_pad_right, live_pad_top, live_pad_bottom = (
            live_virtual_layout.resolve_padding_pixels(
                base_width=display_image1.width,
                base_height=display_image1.height,
            )
            if live_virtual_layout is not None
            else (0, 0, 0, 0)
        )
        pad_left = live_pad_left
        pad_top = live_pad_top
        target_size = (
            display_image1.width + live_pad_left + live_pad_right,
            display_image1.height + live_pad_top + live_pad_bottom,
        )
        store.runtime_cache.overlay_clip_rect = resolve_canvas_clip_rect_px(
            live_virtual_layout,
            base_width=display_image1.width,
            base_height=display_image1.height,
        )

    canvas_w = target_size[0] if target_size is not None else (display_image1.width if display_image1 is not None else 1)
    canvas_h = target_size[1] if target_size is not None else (display_image1.height if display_image1 is not None else 1)
    content_w = content_size[0] if content_size is not None else (display_image1.width if display_image1 is not None else canvas_w)
    content_h = content_size[1] if content_size is not None else (display_image1.height if display_image1 is not None else canvas_h)
    view = vp.view_state
    capture_visible = bool(read_canvas_feature_setting_by_key("image_compare", vp, "capture.visible"))
    capture_color = read_canvas_feature_color_by_setting_key("image_compare", vp, "capture.color")
    _get_guides_state = registry().get_feature_command_by_alias("guides.widget_state")
    guides_state = _get_guides_state(view) if _get_guides_state is not None else _FallbackGuidesState()

    divider_px = (
        int(divider_thickness_px)
        if divider_thickness_px is not None
        else int(
            (
                registry().get_feature_command_by_alias("overlay.active_divider_thickness")
                or (lambda _store: 0)
            )(store)
        )
    )
    guides_px = int(guides_thickness) if guides_thickness is not None else int(guides_state.thickness)

    if render_scene is None:
        render_scene = build_render_scene(
            store,
            apply_channel_mode_in_shader=True,
            clip_overlays_to_image_bounds=False,
        )

    overlay_layout = None
    overlay_enabled_query = registry().get_feature_command_by_alias("overlay.enabled")
    build_overlay_layout = registry().get_feature_command_by_alias(
        "overlay.render_build_layout"
    )
    if (
        overlay_enabled_query is not None
        and build_overlay_layout is not None
        and overlay_enabled_query(store)
    ):
        overlay_layout = build_overlay_layout(
            vp,
            width=max(1, int(content_w)),
            height=max(1, int(content_h)),
            canvas_width=canvas_w,
            canvas_height=canvas_h,
            content_offset_x=float(pad_left),
            content_offset_y=float(pad_top),
            divider_thickness_px=divider_px,
        )

    return CanvasRenderPlan(
        image1=display_image1,
        image2=display_image2,
        source_image1=source_image1,
        source_image2=source_image2,
        source_key=source_key,
        display_cache_key=display_cache_key,
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        render_scene=render_scene,
        overlay_layout=overlay_layout,
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
        guides_thickness=guides_px,
        fill_rgba=(
            None
            if fill_color is None
            else (
                int(fill_color[0]),
                int(fill_color[1]),
                int(fill_color[2]),
                int(fill_color[3]),
            )
            if len(fill_color) >= 4
            else None
        ),
        output_scale=float(output_scale or 1.0),
        preserve_zoom=preserve_zoom,
        image_is_padded_composite=bool(image_is_padded_composite),
        geometry_letterbox=bool(geometry_letterbox),
    )

