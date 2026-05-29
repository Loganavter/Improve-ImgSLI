from __future__ import annotations

from domain.types import Rect
from ui.canvas_infra.scene.widget_registry import (
    apply_canvas_feature_live_runtime_overlays,
    apply_canvas_feature_plan_runtime_overlays,
)

from .plan import CanvasRenderPlan

def _compute_sr(canvas, plan) -> float:
    """
    Return the letterbox scale factor sr = min(dw/canvas_w, dh/canvas_h).

    This is the single coefficient that converts canvas-px → widget-px for
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
    Apply feature-owned plan/runtime overlays after letterbox geometry is known.

    Safe to call even before the widget has been shown (returns early when
    ``_content_rect_px`` is not yet available; ``emit_viewport_state_change``
    will retry after the first resize).

    Always updates ``_inner_content_rect_px`` / ``_inner_split_position`` on the
    runtime state so GL passes (e.g. FilenameOverlayPass) can read the pre-computed
    image rect without re-deriving it from clip_rect every frame.
    """
    state = canvas.runtime_state

    inner_rect, inner_split = _compute_inner_content_rect(state, plan)
    state._inner_content_rect_px = inner_rect
    state._inner_split_position = inner_split
    state._content_sr = _compute_sr(canvas, plan)
    # Re-apply the clip policy after letterbox geometry: update_letterbox_geometry
    # unconditionally resets state._clip_overlays_to_content_rect, so the flag set
    # in _setup_store_bindings (kept on the canvas for scene rebuilds) must be
    # mirrored back onto the runtime state that the GL passes actually read.
    state._clip_overlays_to_content_rect = bool(
        getattr(canvas, "_clip_overlays_to_content_rect", False)
    )

    apply_canvas_feature_plan_runtime_overlays(canvas, plan)

def _sync_geometry_state(canvas, store) -> None:
    """Update store.viewport.geometry_state from the canvas content rect.

    Prefers ``_inner_content_rect_px`` over ``_content_rect_px`` when set —
    the *inner* rect is the actual image-content area inside a padded
    virtual canvas (uncrop / fit-content mode). Without this preference,
    overlay positions in uncrop mode use the full virtual canvas as the
    reference and end up shifted into the padded area.
    """
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
    from ui.widgets.gl_canvas.scene import build_gl_render_scene
    from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias
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
        canvas.set_guides_params(plan.guides_enabled, plan.guides_color, plan.guides_thickness)
        canvas.set_capture_color(plan.capture_color)

    # Compute ``_inner_content_rect_px`` BEFORE syncing geometry — the sync
    # prefers the inner rect when present so feature scene-graph builders
    # (which read ``geometry_state.pixmap_width/height``) operate in
    # image-content coordinates instead of full virtual-canvas coordinates.
    apply_plan_runtime_overlays(canvas, plan)

    if store is not None:
        _sync_geometry_state(canvas, store)

    if store is not None:
        apply_canvas_feature_live_runtime_overlays(store, canvas)

def _textures_are_current(canvas, plan: CanvasRenderPlan) -> bool:
    if plan.display_cache_key is None:
        return False
    state = canvas.runtime_state
    if plan.display_cache_key != state._stored_image_ids:
        return False
    stored = state._stored_pil_images
    return bool(stored and stored[0] is not None)

def apply_canvas_render_plan(
    canvas,
    plan: CanvasRenderPlan,
    *,
    store=None,
    clip_overlays_to_image_bounds: bool = False,
) -> None:
    """
    Unified canvas configurator.

    Automatically detects whether the canvas already holds the same textures
    described by *plan* (via ``display_cache_key``).  When textures are
    current, only the GL scene + overlays are refreshed (no ``set_pil_layers``
    / ``reset_view``).  Otherwise the full texture-upload path runs.

    ``store=None``  —  snapshot / export / preview path; the plan fully
                       describes the frame; zoom is reset; guides and capture
                       overlay params are pushed from the plan.
    ``store=…``     —  interactive path; live feature overlays drive positions,
                       split sync, and geometry; zoom is preserved when
                       ``plan.preserve_zoom`` is True.
    """
    if _textures_are_current(canvas, plan):
        _apply_plan_scene_only(
            canvas, plan,
            store=store,
            clip_overlays_to_image_bounds=clip_overlays_to_image_bounds,
        )
    else:
        _apply_plan_full(
            canvas, plan,
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
    """Full path — uploads textures, resets view, configures everything."""
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
    Lightweight scene-only update — textures are already current.

    Updates GL scene, guides, capture color, runtime overlays, and letterbox
    geometry without calling ``set_pil_layers`` or ``reset_view``.
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
            from ui.widgets.gl_canvas.texture_parts.base_images import (
                update_letterbox_geometry,
            )
            update_letterbox_geometry(canvas, img0, slot_index=0)

        _apply_overlays(canvas, plan, store=store)

    finally:
        if hasattr(canvas, "end_update_batch"):
            canvas.end_update_batch()

def apply_render_plan_to_canvas(canvas, plan: CanvasRenderPlan) -> None:
    """Snapshot / export / preview path — thin wrapper around apply_canvas_render_plan."""
    apply_canvas_render_plan(canvas, plan)
