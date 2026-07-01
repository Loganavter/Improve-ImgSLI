from __future__ import annotations

from domain.types import Rect
from ui.canvas_infra.scene.widget_registry import (
    apply_canvas_feature_live_runtime_overlays,
    apply_canvas_feature_plan_runtime_overlays,
    get_canvas_feature_command_by_alias,
)
from ui.canvas_infra.viewport.focus import (
    capture_letterbox_focus,
    restore_letterbox_focus,
)
from ui.canvas_presentation.plan import CanvasRenderPlan


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

    The *inner* rect is the sub-region of the letterbox display area that contains
    actual image content (i.e. the base image area, excluding fit_content padding).
    When there is no fit_content padding ``overlay_clip_rect`` is ``None`` and the
    inner rect equals the full letterbox display area.

    Returns ``(inner_rect, inner_split)`` where:
    - ``inner_rect`` is a ``(x, y, w, h)`` tuple in widget-px, or ``None`` if
      letterbox geometry is not yet available.
    - ``inner_split`` is the split_position_visual re-expressed as a fraction of
      the inner image rect (so GL passes can position the divider correctly inside
      the inner rect), or ``None`` when no clip_rect padding is active.
    """
    content_rect = state._content_rect_px
    if not content_rect or plan.canvas_w <= 0 or plan.canvas_h <= 0:
        return None, None

    ox, oy, dw, dh = content_rect
    sx = dw / plan.canvas_w
    sy = dh / plan.canvas_h

    clip_rect = getattr(plan.gl_scene, "overlay_clip_rect", None)
    if clip_rect:
        clip_x, clip_y, clip_w, clip_h = clip_rect
        inner = (
            int(round(ox + clip_x * sx)),
            int(round(oy + clip_y * sy)),
            max(1, int(round(clip_w * sx))),
            max(1, int(round(clip_h * sy))),
        )

        raw_split = float(getattr(plan.gl_scene, "split_position_visual", 0.5))
        is_horizontal = bool(getattr(plan.gl_scene, "is_horizontal", False))
        if is_horizontal and clip_h > 0:
            inner_split = max(0.0, min(1.0, (raw_split * plan.canvas_h - clip_y) / clip_h))
        elif not is_horizontal and clip_w > 0:
            inner_split = max(0.0, min(1.0, (raw_split * plan.canvas_w - clip_x) / clip_w))
        else:
            inner_split = None
    else:
        inner = (int(round(ox)), int(round(oy)), max(1, int(round(dw))), max(1, int(round(dh))))
        inner_split = None

    return inner, inner_split


def apply_plan_runtime_overlays(canvas, plan: CanvasRenderPlan) -> None:
    """
    Apply image-compare feature-owned plan/runtime overlays after letterbox geometry is known.
    """
    state = canvas.runtime_state

    inner_rect, inner_split = _compute_inner_content_rect(state, plan)
    state._inner_content_rect_px = inner_rect
    state._inner_split_position = inner_split
    state._content_sr = _compute_sr(canvas, plan)

    state._clip_overlays_to_content_rect = bool(
        getattr(canvas, "_clip_overlays_to_content_rect", False)
    )

    apply_canvas_feature_plan_runtime_overlays(canvas, plan)


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
    from tabs.image_compare.canvas.scene import build_gl_render_scene

    command = get_canvas_feature_command_by_alias("splitter.sync_split_position")
    if command is not None:
        command(type("CanvasActions", (), {"store": store})(), split_position)
    canvas.set_render_scene(
        build_gl_render_scene(
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
    else:
        state._store = None

    canvas._active_render_plan = plan
    canvas._clip_overlays_to_content_rect = clip_flag
    canvas.set_render_scene(plan.gl_scene)

    if store is not None:
        canvas.set_split_position_sync(
            lambda split: _sync_split_position(store, canvas, split)
        )
        canvas.set_apply_channel_mode_in_shader(True)
    else:
        state._apply_channel_mode_in_shader = True


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
        apply_canvas_feature_live_runtime_overlays(store, canvas)


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

        _apply_overlays(canvas, plan, store=store)

    finally:
        if hasattr(canvas, "end_update_batch"):
            canvas.end_update_batch()
