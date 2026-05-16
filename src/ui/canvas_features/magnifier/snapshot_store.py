from __future__ import annotations

from core.store import Store
from domain.types import Point

from .state import get_magnifier_widget_state

def _clone_point(point):
    if point is None:
        return None
    return Point(point.x, point.y)

def _transform_point(point, pad_left, pad_top, base_w, base_h, virtual_w, virtual_h):
    if point is None or base_w <= 0 or base_h <= 0 or virtual_w <= 0 or virtual_h <= 0:
        return None
    return Point(
        (pad_left + point.x * base_w) / virtual_w,
        (pad_top + point.y * base_h) / virtual_h,
    )

def _normalize_capture_position(point, capture_size_relative: float) -> Point | None:
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
    for model in _iter_mutable_magnifier_models(store):
        capture_size = float(getattr(model, "capture_size_relative", 0.0) or 0.0)
        model.position = _normalize_capture_position(model.position, capture_size) or model.position
        model.frozen_position = _normalize_capture_position(model.frozen_position, capture_size)

def retarget_snapshot_store_to_padded_canvas(
    store: Store,
    *,
    pad_left: int,
    pad_right: int,
    pad_top: int,
    pad_bottom: int,
    base_w: int,
    base_h: int,
) -> None:
    virtual_w = base_w + pad_left + pad_right
    virtual_h = base_h + pad_top + pad_bottom
    if virtual_w <= 0 or virtual_h <= 0 or base_w <= 0 or base_h <= 0:
        return

    viewport = store.viewport
    view = viewport.view_state
    viewport.overlay_clip_rect = (pad_left, pad_top, base_w, base_h)
    base_ref = float(max(base_w, base_h))
    virtual_ref = float(max(virtual_w, virtual_h))
    base_min = float(min(base_w, base_h))
    virtual_min = float(min(virtual_w, virtual_h))
    size_scale = (base_ref / virtual_ref) if virtual_ref > 0 else 1.0
    capture_scale = (base_min / virtual_min) if virtual_min > 0 else 1.0

    for model in _iter_mutable_magnifier_models(store):
        model.position = _transform_point(
            _clone_point(model.position),
            pad_left,
            pad_top,
            base_w,
            base_h,
            virtual_w,
            virtual_h,
        ) or model.position
        model.frozen_position = _transform_point(
            _clone_point(model.frozen_position),
            pad_left,
            pad_top,
            base_w,
            base_h,
            virtual_w,
            virtual_h,
        )
        model.capture_size_relative *= capture_scale
        model.size_relative *= size_scale
        model.spacing_relative *= size_scale
        model.offset_relative = Point(
            model.offset_relative.x * size_scale,
            model.offset_relative.y * size_scale,
        )

    if view.is_horizontal:
        view.split_position_visual = (
            pad_top + view.split_position_visual * base_h
        ) / virtual_h
    else:
        view.split_position_visual = (
            pad_left + view.split_position_visual * base_w
        ) / virtual_w
