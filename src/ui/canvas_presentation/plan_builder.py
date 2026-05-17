from __future__ import annotations

from dataclasses import dataclass

from PIL import Image
from PyQt6.QtGui import QColor

from core.store import ImageItem, Store
from ui.canvas_infra.scene.property_access import (
    read_canvas_feature_color_by_setting_key,
    read_canvas_feature_setting_by_key,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias
from ui.widgets.gl_canvas.scene import build_gl_render_scene

from .layout import compute_content_layout
from .models import (
    CanvasTarget,
    PresentationImageSet,
    RenderFramePresentation,
    SnapshotStorePresentation,
)
from .plan import (
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
    overlay_coords: object = None

class _FallbackGuidesState:
    enabled = False
    thickness = 1
    color = type("C", (), {"r": 255, "g": 255, "b": 255, "a": 255})()

def _pad_image(img, width, height, left, top, fill_color=(0, 0, 0, 0)):
    padded = Image.new("RGBA", (width, height), fill_color)
    if img is not None:
        padded.alpha_composite(img.convert("RGBA"), (left, top))
    return padded

def _get_unified_images(image1, image2, fit_content, global_bounds, fill_color=None):
    from shared.image_processing.resize import resize_images_processor

    img1 = image1.convert("RGBA") if image1 is not None else None
    img2 = image2.convert("RGBA") if image2 is not None else None

    if img1 is not None and img2 is not None:
        img1, img2 = resize_images_processor(img1, img2)

    if fit_content and global_bounds:
        pad_left, pad_right, pad_top, pad_bottom, base_w, base_h = global_bounds
        virtual_w = base_w + pad_left + pad_right
        virtual_h = base_h + pad_top + pad_bottom
        if virtual_w > 0 and virtual_h > 0 and base_w > 0 and base_h > 0:
            fill = fill_color or (0, 0, 0, 0)
            img1 = _pad_image(img1, virtual_w, virtual_h, pad_left, pad_top, fill)
            img2 = _pad_image(img2, virtual_w, virtual_h, pad_left, pad_top, fill)

    return img1, img2

def _build_snapshot_store(
    snap,
    image1,
    image2,
    *,
    fit_content: bool = False,
    global_bounds=None,
    fill_color=None,
):
    store = Store()
    store.viewport = snap.viewport_state.clone()
    store.settings = snap.settings_state.freeze_for_export()
    store.viewport.overlay_clip_rect = None
    normalize_snapshot = get_canvas_feature_command_by_alias("overlay.snapshot_normalize")
    if normalize_snapshot is not None:
        normalize_snapshot(store)

    source_img1, source_img2 = _get_unified_images(
        image1, image2, fit_content, global_bounds, fill_color
    )
    display_img1, display_img2 = source_img1, source_img2

    if fit_content and global_bounds:
        pad_left, pad_right, pad_top, pad_bottom, base_w, base_h = global_bounds
        retarget_snapshot = get_canvas_feature_command_by_alias(
            "overlay.snapshot_retarget_to_padded_canvas"
        )
        if retarget_snapshot is not None:
            retarget_snapshot(
                store,
                pad_left=pad_left,
                pad_right=pad_right,
                pad_top=pad_top,
                pad_bottom=pad_bottom,
                base_w=base_w,
                base_h=base_h,
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
    display_cache_key = (
        id(display_img1) if display_img1 is not None else 0,
        id(display_img2) if display_img2 is not None else 0,
        display_img1.size if display_img1 is not None else None,
        display_img2.size if display_img2 is not None else None,
        fit_content,
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
    source_image1 = store.document.full_res_image1 or store.document.original_image1
    source_image2 = store.document.full_res_image2 or store.document.original_image2

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

    build_drawing_coords = get_canvas_feature_command_by_alias(
        "overlay.render_drawing_coords"
    )
    overlay_drawing_coords = None
    if build_drawing_coords is not None:
        overlay_drawing_coords = build_drawing_coords(
            presentation.store,
            drawing_width=render_w,
            drawing_height=render_h,
            container_width=render_w,
            container_height=render_h,
        )

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
        feature_extras={"overlay_drawing_coords": overlay_drawing_coords},
        scaled_image1=scaled_image1,
        scaled_image2=scaled_image2,
    )

def compute_canvas_plan(
    store,
    image_width: int,
    image_height: int,
    overlay_drawing_coords=None,
) -> CanvasGeometry:
    compute_padding = get_canvas_feature_command_by_alias(
        "overlay.render_compute_padding"
    )
    pad_left, pad_right, pad_top, pad_bottom = (
        compute_padding(
            store,
            drawing_width=image_width,
            drawing_height=image_height,
        )
        if compute_padding is not None
        else (0, 0, 0, 0)
    )
    return CanvasGeometry(
        image_width=image_width,
        image_height=image_height,
        canvas_width=image_width + pad_left + pad_right,
        canvas_height=image_height + pad_top + pad_bottom,
        padding_left=pad_left,
        padding_top=pad_top,
        padding_right=pad_right,
        padding_bottom=pad_bottom,
        overlay_coords=overlay_drawing_coords,
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
        output_scale=float(output_scale or 1.0),
        preserve_zoom=preserve_zoom,
    )
