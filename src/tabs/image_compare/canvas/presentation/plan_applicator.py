from __future__ import annotations

from domain.types import Rect
from ui.canvas_infra.scene.frame_geometry import resolve_canvas_content_geometry
from tabs.image_compare.canvas.registry import registry
from ui.canvas_infra.viewport.focus import (
    capture_letterbox_focus,
    restore_letterbox_focus,
)
from ui.canvas_presentation.plan import CanvasRenderPlan


def _plan_owns_padded_framebuffer(plan) -> bool:
    """True when ``canvas_w/h`` is the padded frame and clip/letterbox apply.

    Live main-window plans may carry ``overlay_clip_rect`` for uncrop without
    owning letterbox (images still fit by raw size). Export/video snapshot
    plans set ``geometry_letterbox`` for that ownership instead of baking
    pads into pixels (``image_is_padded_composite``).
    """
    return bool(
        getattr(plan, "image_is_padded_composite", False)
        or getattr(plan, "geometry_letterbox", False)
    )


def _refresh_live_content_rect(canvas, state, plan) -> None:
    """``state._content_rect_px`` is otherwise only refreshed by
    ``letterbox_pil``/``update_letterbox_geometry`` on image upload, which
    leaves it stale after a resize until the next image upload. Re-derive it
    every call for the live, store-backed canvas.

    Live (default): fit raw image size. Export/video with
    ``geometry_letterbox`` / padded composite: fit the full ``canvas_w/h``
    frame so ``overlay_clip_rect`` can recover the content box.

    Padded plans must refresh even when ``state._store`` is unset: video
    preview binds the store on ``canvas._store``, and ``set_pil_layers``
    clears ``state._store``. Skipping here leaves ``_content_rect_px`` as the
    raw-image letterbox; ``_compute_inner_content_rect`` then scales
    ``overlay_clip_rect`` against the wrong base, so the divider detaches
    from the images and stretches into the uncrop pad.
    """
    owns_padded = _plan_owns_padded_framebuffer(plan)
    if not owns_padded:
        store = getattr(state, "_store", None) or getattr(canvas, "_store", None)
        if store is None:
            return
        base_image = plan.image1
        fit_width = getattr(base_image, "width", 0)
        fit_height = getattr(base_image, "height", 0)
    else:
        fit_width, fit_height = plan.canvas_w, plan.canvas_h
    if fit_width <= 0 or fit_height <= 0:
        return
    widget_width, widget_height = canvas.width(), canvas.height()
    if widget_width <= 0 or widget_height <= 0:
        return
    geometry = resolve_canvas_content_geometry(
        widget_width=widget_width,
        widget_height=widget_height,
        image_width=fit_width,
        image_height=fit_height,
        virtual_layout=None,
    )
    if geometry.outer_rect_px is not None:
        state._content_rect_px = geometry.outer_rect_px


def _compute_sr(canvas, plan) -> float:
    """
    Return the letterbox scale factor sr = min(dw/canvas_w, dh/canvas_h).

    This is the single coefficient that converts canvas-px -> widget-px for
    isotropic attributes (border_width, divider_thickness, safe_gap).
    Returns 1.0 when geometry is not yet available (safe for export paths).
    """
    content_rect = canvas.runtime_state._content_rect_px
    if not content_rect or plan.canvas_w <= 0 or plan.canvas_h <= 0:
        return 1.0
    _, _, dw, dh = content_rect
    return min(dw / plan.canvas_w, dh / plan.canvas_h)


def _compute_inner_content_rect(state, plan):
    """
    Compute the inner image rect in widget-px and the corresponding split position.

    The base image pair is never padding-aware (see
    ``_refresh_live_content_rect``/``update_letterbox_geometry``): whenever
    the plan does not own a padded framebuffer, ``inner == outer ==
    _content_rect_px`` — live ``overlay_clip_rect`` must not shrink letterbox.

    When ``image_is_padded_composite`` or ``geometry_letterbox`` is set, honor
    ``overlay_clip_rect`` to narrow back down to the real image region.
    """
    content_rect = state._content_rect_px
    if not content_rect:
        return None, None

    if plan.canvas_w <= 0 or plan.canvas_h <= 0 or not _plan_owns_padded_framebuffer(plan):
        ox, oy, dw, dh = content_rect
        return (
            (int(round(ox)), int(round(oy)), max(1, int(round(dw))), max(1, int(round(dh)))),
            None,
        )

    ox, oy, dw, dh = content_rect
    sx = dw / plan.canvas_w
    sy = dh / plan.canvas_h

    clip_rect = getattr(plan.render_scene, "overlay_clip_rect", None)
    if clip_rect is None:
        inner = (
            int(round(ox)),
            int(round(oy)),
            max(1, int(round(dw))),
            max(1, int(round(dh))),
        )
        return inner, None

    clip_x, clip_y, clip_w, clip_h = clip_rect
    inner = (
        int(round(ox + clip_x * sx)),
        int(round(oy + clip_y * sy)),
        max(1, int(round(clip_w * sx))),
        max(1, int(round(clip_h * sy))),
    )

    raw_split = float(getattr(plan.render_scene, "split_position_visual", 0.5))
    inner_split = max(0.0, min(1.0, raw_split))
    return inner, inner_split


def _apply_plan_letterbox_from_clip(canvas, plan) -> None:
    """Place unpadded export/video images via shader letterbox.

    ``overlay_clip_rect`` is in canvas-px. The preview/export widget may be a
    different size than ``canvas_w/h``, so first fit the padded canvas frame
    into the widget, then nest the clip inside that frame. Applying clip/canvas
    fractions directly as widget UV stretches the image to the pane (wrong for
    video preview).

    Pad fill is painted by the base shader inside the canvas frame only
    (``_canvas_frame_letterbox`` + ``_letterbox_fill_rgba``); widget chrome
    outside the frame stays the theme clear color.
    """
    state = canvas.runtime_state
    state._canvas_frame_letterbox = None
    state._letterbox_fill_rgba = None

    if not bool(getattr(plan, "geometry_letterbox", False)):
        return
    if bool(getattr(plan, "image_is_padded_composite", False)):
        # Baked canvas-sized images already match the framebuffer 1:1.
        return
    clip = getattr(getattr(plan, "render_scene", None), "overlay_clip_rect", None)
    cw = int(getattr(plan, "canvas_w", 0) or 0)
    ch = int(getattr(plan, "canvas_h", 0) or 0)
    if clip is None or cw <= 0 or ch <= 0:
        return

    widget_w = int(canvas.width()) if callable(getattr(canvas, "width", None)) else 0
    widget_h = int(canvas.height()) if callable(getattr(canvas, "height", None)) else 0
    if widget_w <= 0 or widget_h <= 0:
        return

    frame = resolve_canvas_content_geometry(
        widget_width=widget_w,
        widget_height=widget_h,
        image_width=cw,
        image_height=ch,
        virtual_layout=None,
    )
    inner = frame.inner_rect_px
    if inner is None:
        return
    ox, oy, fw, fh = inner
    if fw <= 0 or fh <= 0:
        return

    cx, cy, cww, chh = clip
    sx = float(fw) / float(cw)
    sy = float(fh) / float(ch)
    params = (
        (float(ox) + float(cx) * sx) / float(widget_w),
        (float(oy) + float(cy) * sy) / float(widget_h),
        (float(cww) * sx) / float(widget_w),
        (float(chh) * sy) / float(widget_h),
    )
    while len(state._letterbox_params) < 2:
        state._letterbox_params.append((0.0, 0.0, 1.0, 1.0))
    state._letterbox_params[0] = params
    state._letterbox_params[1] = params
    state._canvas_frame_letterbox = (
        float(ox) / float(widget_w),
        float(oy) / float(widget_h),
        float(fw) / float(widget_w),
        float(fh) / float(widget_h),
    )
    fill = getattr(plan, "fill_rgba", None)
    if fill is not None and len(fill) >= 4:
        state._letterbox_fill_rgba = (
            float(fill[0]),
            float(fill[1]),
            float(fill[2]),
            float(fill[3]),
        )



def apply_plan_runtime_overlays(canvas, plan: CanvasRenderPlan) -> None:
    """
    Apply image-compare feature-owned plan/runtime overlays after letterbox geometry is known.
    """
    state = canvas.runtime_state

    # Widget resize (video preview splitter, window drag) runs
    # ``update_common_letterbox_geometry`` first, which fits the *raw* image.
    # Uncrop plans must re-nest that letterbox inside the padded canvas frame
    # before content/inner rects and DividerPass read them — otherwise images
    # and the spit line diverge after every preview pane resize.
    if _plan_owns_padded_framebuffer(plan):
        _apply_plan_letterbox_from_clip(canvas, plan)

    _refresh_live_content_rect(canvas, state, plan)

    inner_rect, inner_split = _compute_inner_content_rect(state, plan)
    state._inner_content_rect_px = inner_rect
    state._inner_split_position = inner_split
    state._content_sr = _compute_sr(canvas, plan)

    state._clip_overlays_to_content_rect = bool(
        getattr(canvas, "_clip_overlays_to_content_rect", False)
    )

    registry().apply_feature_plan_runtime_overlays(canvas, plan)


def sync_geometry_state(canvas, store) -> None:
    """Update store.viewport.geometry_state from the canvas content rect."""
    state = canvas.runtime_state
    rect = getattr(state, "_inner_content_rect_px", None) or state._content_rect_px
    if not rect:
        return
    cx, cy, cw, ch = rect
    vp = getattr(store, "viewport", None)
    if vp is not None and cw > 0 and ch > 0:
        vp.geometry_state.pixmap_width = cw
        vp.geometry_state.pixmap_height = ch
        vp.geometry_state.image_display_rect_on_label = Rect(cx, cy, cw, ch)


def _sync_split_position(store, canvas, split_position: float) -> None:
    from tabs.image_compare.canvas.scene import build_render_scene

    command = registry().get_feature_command_by_alias("splitter.sync_split_position")
    if command is not None:
        command(type("CanvasActions", (), {"store": store})(), split_position)
    canvas.set_render_scene(
        build_render_scene(
            store,
            apply_channel_mode_in_shader=getattr(canvas, "_apply_channel_mode_in_shader", True),
            clip_overlays_to_image_bounds=getattr(canvas, "_clip_overlays_to_content_rect", False),
        )
    )


def _resolve_clip_flag(store, clip_overlays_to_image_bounds: bool, plan) -> bool:
    if store is not None:
        return clip_overlays_to_image_bounds
    return False


def _setup_store_bindings(canvas, plan, *, store, clip_flag: bool) -> None:
    state = canvas.runtime_state

    if store is not None:
        canvas._store = store
        state._store = store
    else:
        canvas._store = None
        state._store = None

    canvas._active_render_plan = plan
    canvas._clip_overlays_to_content_rect = clip_flag
    canvas.set_render_scene(plan.render_scene)

    if store is not None:
        canvas.set_split_position_sync(
            lambda split: _sync_split_position(store, canvas, split)
        )
        canvas.set_apply_channel_mode_in_shader(True)
    else:
        state._apply_channel_mode_in_shader = True


def _rebind_plan_store(canvas, store) -> None:
    """``set_pil_layers`` clears ``state._store``; restore after texture upload."""
    if store is None:
        return
    canvas._store = store
    canvas.runtime_state._store = store


def _apply_overlays(canvas, plan, *, store) -> None:
    if store is None:
        canvas.set_guides_params(
            plan.guides_enabled,
            plan.guides_color,
            plan.guides_thickness,
        )
        canvas.set_capture_color(plan.capture_color)

    apply_plan_runtime_overlays(canvas, plan)

    if store is not None:
        sync_geometry_state(canvas, store)
        registry().apply_feature_live_runtime_overlays(store, canvas)


def _textures_are_current(canvas, plan: CanvasRenderPlan) -> bool:
    if plan.display_cache_key is None:
        return False
    state = canvas.runtime_state
    if plan.display_cache_key != state._stored_image_ids:
        return False
    stored = state._stored_pil_images
    return bool(stored and stored[0] is not None)


def apply_legacy_canvas_render_plan(
    canvas,
    plan: CanvasRenderPlan,
    *,
    store=None,
    clip_overlays_to_image_bounds: bool = False,
) -> None:
    canvas._active_composition = None
    if _textures_are_current(canvas, plan):
        _apply_plan_scene_only(
            canvas,
            plan,
            store=store,
            clip_overlays_to_image_bounds=clip_overlays_to_image_bounds,
        )
    else:
        _apply_plan_full(
            canvas,
            plan,
            store=store,
            clip_overlays_to_image_bounds=clip_overlays_to_image_bounds,
        )


def _apply_plan_full(
    canvas,
    plan: CanvasRenderPlan,
    *,
    store,
    clip_overlays_to_image_bounds: bool,
) -> None:
    """Full path: uploads textures, resets view, configures everything."""
    from ui.canvas_infra.viewport.state import (
        get_pan_offset_x,
        get_pan_offset_y,
        get_zoom_level,
        set_pan_offsets,
        set_zoom_level,
    )

    if hasattr(canvas, "begin_update_batch"):
        canvas.begin_update_batch()
    try:
        clip_flag = _resolve_clip_flag(store, clip_overlays_to_image_bounds, plan)
        _setup_store_bindings(canvas, plan, store=store, clip_flag=clip_flag)

        if plan.preserve_zoom:
            zoom_level = get_zoom_level(canvas)
            pan_x = get_pan_offset_x(canvas)
            pan_y = get_pan_offset_y(canvas)
            letterbox_focus = capture_letterbox_focus(canvas)
        canvas.reset_view()
        if plan.preserve_zoom:
            set_zoom_level(canvas, zoom_level)
            set_pan_offsets(canvas, pan_x, pan_y)
            zoom_signal = getattr(canvas, "zoomChanged", None)
            if zoom_signal is not None and abs(zoom_level - 1.0) > 1e-6:
                zoom_signal.emit(zoom_level)
        else:
            set_zoom_level(canvas, 1.0)
            set_pan_offsets(canvas, 0.0, 0.0)

        canvas.set_pil_layers(
            plan.image1,
            plan.image2,
            source_image1=plan.source_image1,
            source_image2=plan.source_image2,
            source_key=plan.source_key,
            display_cache_key=plan.display_cache_key,
            shader_letterbox=True,
        )
        _rebind_plan_store(canvas, store)
        _apply_plan_letterbox_from_clip(canvas, plan)
        if plan.preserve_zoom:
            restore_letterbox_focus(canvas, letterbox_focus)

        _apply_overlays(canvas, plan, store=store)

    finally:
        if hasattr(canvas, "end_update_batch"):
            canvas.end_update_batch()


def _apply_plan_scene_only(
    canvas,
    plan: CanvasRenderPlan,
    *,
    store,
    clip_overlays_to_image_bounds: bool,
) -> None:
    """
    Lightweight scene-only update: textures are already current.
    """
    from ui.canvas_infra.viewport.state import (
        get_zoom_level,
        set_pan_offsets,
        set_zoom_level,
    )

    if hasattr(canvas, "begin_update_batch"):
        canvas.begin_update_batch()
    try:
        clip_flag = _resolve_clip_flag(store, clip_overlays_to_image_bounds, plan)
        _setup_store_bindings(canvas, plan, store=store, clip_flag=clip_flag)

        if not plan.preserve_zoom:
            if abs(get_zoom_level(canvas) - 1.0) > 1e-6:
                set_zoom_level(canvas, 1.0)
            set_pan_offsets(canvas, 0.0, 0.0)

        state = canvas.runtime_state
        img0 = state._stored_pil_images[0] if state._stored_pil_images else None
        if img0 is not None and state._shader_letterbox_mode:
            letterbox_focus = capture_letterbox_focus(canvas) if plan.preserve_zoom else None
            from tabs.image_compare.canvas.texture_parts.base_images import (
                update_common_letterbox_geometry,
            )

            img1 = (
                state._stored_pil_images[1]
                if len(state._stored_pil_images) > 1
                else None
            )
            update_common_letterbox_geometry(canvas, img0, img1)
            restore_letterbox_focus(canvas, letterbox_focus)
        _rebind_plan_store(canvas, store)
        _apply_plan_letterbox_from_clip(canvas, plan)

        _apply_overlays(canvas, plan, store=store)

    finally:
        if hasattr(canvas, "end_update_batch"):
            canvas.end_update_batch()
