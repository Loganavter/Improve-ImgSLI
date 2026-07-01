"""Snapshot-store helpers called by the video export/preview pipeline.

There are two entry points, exposed as capability aliases:

- ``overlay.snapshot_normalize`` — called in CROP mode to clamp magnifier
  capture positions so the capture rect stays inside the image bounds.
- ``overlay.snapshot_apply_virtual_layout`` — called in UNCROP / fit-content
  mode. Historically this mutated model coordinates to "pre-bake" the
  virtual-canvas transform into the store; that was wrong because the
  renderer already handles virtual padding via ``content_offset_x/y``,
  ``content_w/h``, and ``canvas_w/h`` (see ``layout_plan.py``), and applying
  the transform a second time at store level produced double shifts. The
  function now only logs the layout for debugging; coordinate adjustment is
  the renderer's job.

The interactive scene and the export scene must produce identical visuals
given identical inputs (the only intentional asymmetry is that the video
editor reads keyframes that the interactive scene writes). Any "fix" applied
in the export-only path that has no interactive counterpart is a code smell.
"""

from __future__ import annotations

import logging

from core.store import Store
from domain.types import Point

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
) -> None:
    """No-op debug hook for the uncrop / fit-content path.

    The renderer takes ``content_offset_x/y`` and ``content_w/h`` and produces
    correct overlay positions on a padded virtual canvas without any
    per-model adjustment. Likewise ``apply_virtual_canvas_layout_to_scene``
    in ``tabs/image_compare/services/gpu_export_scene.py`` shifts
    ``split_position_visual`` and sets ``overlay_clip_rect`` at the scene
    level. Mutating the store here on top of that would double-compensate.
    """
    canvas_bounds = virtual_layout.canvas_bounds
    _mlog.debug(
        "snapshot_virtual_layout(noop) base=%sx%s canvas_bounds=(%.4f,%.4f,%.4f,%.4f)",
        base_w,
        base_h,
        float(canvas_bounds.x_min),
        float(canvas_bounds.y_min),
        float(canvas_bounds.x_max),
        float(canvas_bounds.y_max),
    )
