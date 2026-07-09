"""Snapshot-store helpers called by the video export/preview pipeline.

There are two entry points, exposed as capability aliases:

- ``overlay.snapshot_normalize`` — called in CROP mode to clamp magnifier
  capture positions so the capture rect stays inside the image bounds.
- ``overlay.snapshot_apply_virtual_layout`` — called in UNCROP / fit-content
  mode. Historically this mutated *magnifier model* coordinates to "pre-bake"
  the virtual-canvas transform into the store; that was wrong because the
  magnifier already handles virtual padding via ``content_offset_x/y``,
  ``content_w/h``, and ``canvas_w/h`` passed straight into ``layout_plan.py``,
  so mutating model coordinates here produced double shifts for it.

  It also used to hand-roll a re-expression of
  ``store.viewport.view_state.split_position_visual`` against the padded
  canvas. That duplicated the one thing
  ``docs/dev/CANVAS_CONTENT_GEOMETRY_REFACTOR.md`` says must never be
  recombined by hand outside ``ui/canvas_infra/viewport/zoom.py`` — dropped.
  This function only sets ``store.runtime_cache.overlay_clip_rect`` (via the
  shared ``resolve_canvas_clip_rect_px`` helper, the single owner of that
  computation), which is a throwaway snapshot ``Store`` field with no live
  per-frame pass to populate it otherwise.

The interactive scene and the export scene must produce identical visuals
given identical inputs (the only intentional asymmetry is that the video
editor reads keyframes that the interactive scene writes). Any "fix" applied
in the export-only path that has no interactive counterpart is a code smell.
"""

from __future__ import annotations

import logging

from core.store import Store
from domain.types import Point
from ui.canvas_infra.scene.frame_geometry import resolve_canvas_clip_rect_px

from .state import get_magnifier_widget_state

_mlog = logging.getLogger("ImproveImgSLI.video_magnifier_layout")


def _normalize_capture_position(point, capture_size_relative: float) -> Point | None:
    """Clamp the capture-rect center so the rect stays inside [0..1]."""
    if point is None:
        return None
    radius = max(0.0, float(capture_size_relative)) / 2.0
    min_pos = min(0.5, radius)
    max_pos = max(min_pos, 1.0 - radius)
    return Point(
        max(min_pos, min(max_pos, float(point.x))),
        max(min_pos, min(max_pos, float(point.y))),
    )


def _iter_mutable_magnifier_models(store: Store):
    view = store.viewport.view_state
    state = get_magnifier_widget_state(view)
    return [model for model in state.models.values() if model is not None]


def normalize_snapshot_store(store: Store) -> None:
    """Clamp magnifier capture positions so the capture rect stays inside image bounds.

    Called in CROP mode of the video export/preview pipeline. Without this,
    a capture rect that was edited near the image edge can extend outside the
    cropped image and the magnifier samples garbage / mis-positions.
    """
    for model in _iter_mutable_magnifier_models(store):
        capture_size = float(getattr(model, "capture_size_relative", 0.0) or 0.0)
        model.position = (
            _normalize_capture_position(model.position, capture_size) or model.position
        )
        model.frozen_position = _normalize_capture_position(
            model.frozen_position, capture_size
        )


def apply_virtual_canvas_layout_to_snapshot_store(
    store: Store,
    *,
    base_w: int,
    base_h: int,
    virtual_layout,
    content_offset_x: int = 0,
    content_offset_y: int = 0,
    content_w: int | None = None,
    content_h: int | None = None,
) -> None:
    """Wire the resolved virtual-canvas layout into store/scene-level fields.

    ``base_w``/``base_h`` is the un-padded content box the real image was
    fitted into; ``content_offset_x/y`` + ``content_w/h`` additionally account
    for centering when the source had to be scaled down to fit that box (0 /
    ``None`` when no such extra fit-down happened, i.e. the common case).
    ``virtual_layout.canvas_bounds`` gives the feature-driven padding around
    that box, in the same normalized base-image units used everywhere else in
    the layout contract (see ``shared/rendering/layout_contract.py``).

    Sets:
    - ``store.runtime_cache.overlay_clip_rect`` — where the real image sits
      inside the padded canvas, in canvas pixel units. Consumed by
      ``build_render_scene`` -> ``RenderScene.overlay_clip_rect`` ->
      ``_inner_content_rect_px`` (divider clip/position, split-position
      screen mapping, capture-area clamping).
    """
    store.runtime_cache.overlay_clip_rect = resolve_canvas_clip_rect_px(
        virtual_layout,
        base_width=base_w,
        base_height=base_h,
        content_offset_px=(content_offset_x, content_offset_y),
        content_size_px=(
            (content_w, content_h) if content_w is not None and content_h is not None else None
        ),
    )

    _mlog.debug(
        "snapshot_virtual_layout base=%sx%s canvas_bounds=%s clip_rect=%s",
        base_w,
        base_h,
        getattr(virtual_layout, "canvas_bounds", None),
        store.runtime_cache.overlay_clip_rect,
    )
