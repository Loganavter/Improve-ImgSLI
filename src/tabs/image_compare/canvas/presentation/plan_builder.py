from __future__ import annotations

import logging
from dataclasses import dataclass

from PIL import Image

_pblog = logging.getLogger("ImproveImgSLI.plan_builder")
from PySide6.QtGui import QColor

from core.store import Store
from tabs.image_compare.state.document import ImageItem
from shared.rendering import VirtualCanvasLayout, resolve_virtual_canvas_layout
from ui.canvas_infra.scene.property_access import (
    read_canvas_feature_color_by_setting_key,
    read_canvas_feature_setting_by_key,
)
from ui.canvas_infra.scene.widget_registry import (
    get_canvas_feature_command_by_alias,
    get_canvas_feature_commands_by_id,
)
from tabs.image_compare.canvas.scene import build_gl_render_scene

from ui.canvas_presentation.layout import compute_content_layout
from ui.canvas_presentation.models import (
    CanvasTarget,
    PresentationImageSet,
    RenderFramePresentation,
    SnapshotStorePresentation,
)
from ui.canvas_presentation.plan import (
    CanvasRenderPlan,
)

@dataclass(frozen=True)
class CanvasGeometry:
    image_width: int
    image_height: int
    canvas_width: int
    canvas_height: int
    padding_left: int
    padding_top: int
    padding_right: int
    padding_bottom: int
    virtual_layout: VirtualCanvasLayout | None = None

class _FallbackGuidesState:
    enabled = False
    thickness = 1
    color = type("C", (), {"r": 255, "g": 255, "b": 255, "a": 255})()

def _resolve_overlay_virtual_layout(
    store,
    *,
    drawing_width: int,
    drawing_height: int,
) -> VirtualCanvasLayout | None:
    requirements = []
    for build_requirement in get_canvas_feature_commands_by_id(
        "render.layout_requirement"
    ):
        requirement = build_requirement(
            store,
            drawing_width=drawing_width,
            drawing_height=drawing_height,
        )
        if requirement is not None:
            requirements.append(requirement)
    return resolve_virtual_canvas_layout(requirements)

def _resolve_overlay_padding(
    store,
    *,
    drawing_width: int,
    drawing_height: int,
) -> tuple[tuple[int, int, int, int], VirtualCanvasLayout | None]:
    layout = _resolve_overlay_virtual_layout(
        store,
        drawing_width=drawing_width,
        drawing_height=drawing_height,
    )
    if layout is None:
        return (0, 0, 0, 0), None
    padding = layout.resolve_padding_pixels(
        base_width=drawing_width,
        base_height=drawing_height,
    )
    return (
        padding,
        layout,
    )

def _pad_image(img, width, height, left, top, fill_color=(0, 0, 0, 0)):
    padded = Image.new("RGBA", (width, height), fill_color)
    if img is not None:
        padded.alpha_composite(img.convert("RGBA"), (left, top))
    return padded

def _get_unified_images(
    image1,
    image2,
    fit_content,
    global_bounds,
    fill_color=None,
    *,
    resize_method: str = "LANCZOS",
):
    from shared.image_processing.resize import resize_images_processor

    img1 = image1.convert("RGBA") if image1 is not None else None
    img2 = image2.convert("RGBA") if image2 is not None else None

    if img1 is not None and img2 is not None:
        img1, img2 = resize_images_processor(img1, img2, resize_method)

    return img1, img2

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
    store.viewport = snap.viewport_state.clone()
    store.settings = snap.settings_state.freeze_for_export()
    store.runtime_cache.overlay_clip_rect = None
    normalize_snapshot_command = get_canvas_feature_command_by_alias("overlay.snapshot_normalize")
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
        if virtual_w > 0 and virtual_h > 0 and base_w > 0 and base_h > 0:
            fill = fill_color or (0, 0, 0, 0)
            fitted1, fitted2 = source_img1, source_img2
            img_w = fitted1.width if fitted1 else 0
            img_h = fitted1.height if fitted1 else 0
            did_fit_down = False
            if img_w > base_w or img_h > base_h:
                fit_r = min(base_w / max(1, img_w), base_h / max(1, img_h))
                new_w = max(1, int(img_w * fit_r))
                new_h = max(1, int(img_h * fit_r))
                if fitted1 is not None:
                    fitted1 = fitted1.resize((new_w, new_h), Image.Resampling.LANCZOS)
                if fitted2 is not None:
                    fitted2 = fitted2.resize((new_w, new_h), Image.Resampling.LANCZOS)
                img_w, img_h = new_w, new_h
                did_fit_down = True
            img_offset_x = (base_w - img_w) // 2
            img_offset_y = (base_h - img_h) // 2
            display_img1 = _pad_image(
                fitted1, virtual_w, virtual_h, pad_left + img_offset_x, pad_top + img_offset_y, fill
            )
            display_img2 = _pad_image(
                fitted2, virtual_w, virtual_h, pad_left + img_offset_x, pad_top + img_offset_y, fill
            )
        apply_virtual_layout = get_canvas_feature_command_by_alias(
            "overlay.snapshot_apply_virtual_layout"
        )
        if apply_virtual_layout is not None:
            apply_virtual_layout(
                store,
                base_w=base_w,
                base_h=base_h,
                virtual_layout=global_bounds.to_virtual_layout(),
            )
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
    store.document.full_res_image1 = source_img1
    store.document.full_res_image2 = source_img2
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

def build_live_store_presentation(store) -> SnapshotStorePresentation:
    cache = store.viewport.session_data.render_cache
    display_image1 = (
        cache.display_cache_image1
        or cache.scaled_image1_for_display
        or store.viewport.session_data.image_state.image1
    )
    display_image2 = (
        cache.display_cache_image2
        or cache.scaled_image2_for_display
        or store.viewport.session_data.image_state.image2
    )
    # The live high-resolution source pair must use the same unified canvas
    # coordinate system as the display pair. Document full-res images may have
    # different dimensions; binding them directly makes each side use a
    # different letterbox transform after zooming.
    source_image1 = (
        store.viewport.session_data.image_state.image1
        or store.document.full_res_image1
        or store.document.preview_image1
        or store.document.original_image1
    )
    source_image2 = (
        store.viewport.session_data.image_state.image2
        or store.document.full_res_image2
        or store.document.preview_image2
        or store.document.original_image2
    )

    if display_image1 is None and source_image1 is not None:
        display_image1 = source_image1
    if display_image2 is None and source_image2 is not None:
        display_image2 = source_image2

    source_key = (
        store.document.image1_path,
        store.document.image2_path,
        id(source_image1) if source_image1 is not None else 0,
        id(source_image2) if source_image2 is not None else 0,
        source_image1.size if source_image1 is not None else None,
        source_image2.size if source_image2 is not None else None,
    )
    display_cache_key = (
        id(display_image1) if display_image1 is not None else 0,
        id(display_image2) if display_image2 is not None else 0,
        display_image1.size if display_image1 is not None else None,
        display_image2.size if display_image2 is not None else None,
    )

    return SnapshotStorePresentation(
        store=store,
        images=PresentationImageSet(
            display_image1=display_image1,
            display_image2=display_image2,
            source_image1=source_image1 or display_image1,
            source_image2=source_image2 or display_image2,
            source_key=source_key,
            display_cache_key=display_cache_key,
        ),
        virtual_layout=None,
    )

def build_render_frame_presentation(
    presentation: SnapshotStorePresentation,
    *,
    output_width: int | None = None,
    output_height: int | None = None,
    target: CanvasTarget | None = None,
) -> RenderFramePresentation:
    display_img1 = presentation.display_image1
    display_img2 = presentation.display_image2
    if display_img1 is None or display_img2 is None:
        raise ValueError("Render frame presentation requires both display images.")

    resolved_target = target or CanvasTarget(
        width=max(1, int(output_width or 1)),
        height=max(1, int(output_height or 1)),
        fill_rgba=presentation.fill_rgba,
    )
    layout = compute_content_layout(
        resolved_target,
        image_width=display_img1.width,
        image_height=display_img1.height,
    )
    render_w = layout.content_width
    render_h = layout.content_height
    image_dest_x = layout.content_x
    image_dest_y = layout.content_y

    presentation.store.viewport.geometry_state.pixmap_width = render_w
    presentation.store.viewport.geometry_state.pixmap_height = render_h

    scaled_image1 = display_img1.resize((render_w, render_h), Image.Resampling.BILINEAR)
    scaled_image2 = display_img2.resize((render_w, render_h), Image.Resampling.BILINEAR)

    return RenderFramePresentation(
        store=presentation.store,
        images=presentation.images,
        target=resolved_target,
        layout=layout,
        render_width=render_w,
        render_height=render_h,
        image_dest_x=image_dest_x,
        image_dest_y=image_dest_y,
        scaled_image1=scaled_image1,
        scaled_image2=scaled_image2,
        virtual_layout=presentation.virtual_layout,
    )

def compute_canvas_plan(
    store,
    image_width: int,
    image_height: int,
) -> CanvasGeometry:
    padding, virtual_layout = _resolve_overlay_padding(
        store,
        drawing_width=image_width,
        drawing_height=image_height,
    )
    pad_left, pad_right, pad_top, pad_bottom = padding
    return CanvasGeometry(
        image_width=image_width,
        image_height=image_height,
        canvas_width=image_width + pad_left + pad_right,
        canvas_height=image_height + pad_top + pad_bottom,
        padding_left=pad_left,
        padding_top=pad_top,
        padding_right=pad_right,
        padding_bottom=pad_bottom,
        virtual_layout=virtual_layout,
    )

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
    gl_scene=None,
    divider_thickness_px: int | None = None,
    guides_thickness: int | None = None,
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

    canvas_w = target_size[0] if target_size is not None else (display_image1.width if display_image1 is not None else 1)
    canvas_h = target_size[1] if target_size is not None else (display_image1.height if display_image1 is not None else 1)
    content_w = content_size[0] if content_size is not None else (display_image1.width if display_image1 is not None else canvas_w)
    content_h = content_size[1] if content_size is not None else (display_image1.height if display_image1 is not None else canvas_h)
    view = vp.view_state
    capture_visible = bool(read_canvas_feature_setting_by_key(vp, "capture.visible"))
    capture_color = read_canvas_feature_color_by_setting_key(vp, "capture.color")
    _get_guides_state = get_canvas_feature_command_by_alias("guides.widget_state")
    guides_state = _get_guides_state(view) if _get_guides_state is not None else _FallbackGuidesState()

    divider_px = (
        int(divider_thickness_px)
        if divider_thickness_px is not None
        else int(
            (
                get_canvas_feature_command_by_alias("overlay.active_divider_thickness")
                or (lambda _store: 0)
            )(store)
        )
    )
    guides_px = int(guides_thickness) if guides_thickness is not None else int(guides_state.thickness)

    if gl_scene is None:
        gl_scene = build_gl_render_scene(
            store,
            apply_channel_mode_in_shader=True,
            clip_overlays_to_image_bounds=False,
        )

    overlay_layout = None
    overlay_enabled_query = get_canvas_feature_command_by_alias("overlay.enabled")
    build_overlay_layout = get_canvas_feature_command_by_alias(
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
        gl_scene=gl_scene,
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
        fill_rgba=fill_color or None,
        output_scale=float(output_scale or 1.0),
        preserve_zoom=preserve_zoom,
    )
