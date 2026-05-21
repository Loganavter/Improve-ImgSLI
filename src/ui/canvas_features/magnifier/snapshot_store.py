from __future__ import annotations

import logging

from core.store import Store

from .state import get_magnifier_widget_state

_mlog = logging.getLogger("ImproveImgSLI.video_magnifier_layout")

def _iter_mutable_magnifier_models(store: Store):
    view = store.viewport.view_state
    state = get_magnifier_widget_state(view)
    return [model for model in state.models.values() if model is not None]

def normalize_snapshot_store(store: Store) -> None:
    models = []
    for model in _iter_mutable_magnifier_models(store):
        models.append(
            {
                "id": getattr(model, "id", None),
                "position": (
                    None
                    if getattr(model, "position", None) is None
                    else (
                        float(model.position.x),
                        float(model.position.y),
                    )
                ),
                "frozen_position": (
                    None
                    if getattr(model, "frozen_position", None) is None
                    else (
                        float(model.frozen_position.x),
                        float(model.frozen_position.y),
                    )
                ),
                "capture_size_relative": float(
                    getattr(model, "capture_size_relative", 0.0) or 0.0
                ),
            }
        )

def apply_virtual_canvas_layout_to_snapshot_store(
    store: Store,
    *,
    base_w: int,
    base_h: int,
    virtual_layout,
) -> None:
    canvas_bounds = virtual_layout.canvas_bounds
    content_bounds = virtual_layout.content_bounds
    virtual_w = max(1.0, float(canvas_bounds.width) * float(base_w))
    virtual_h = max(1.0, float(canvas_bounds.height) * float(base_h))
    if virtual_w <= 0 or virtual_h <= 0 or base_w <= 0 or base_h <= 0:
        return

    store.viewport.overlay_clip_rect = None
    models = [
        {
            "id": getattr(model, "id", None),
            "position": (float(model.position.x), float(model.position.y)),
            "frozen_position": (
                None
                if model.frozen_position is None
                else (
                    float(model.frozen_position.x),
                    float(model.frozen_position.y),
                )
            ),
            "capture_size_relative": float(model.capture_size_relative),
            "size_relative": float(model.size_relative),
            "spacing_relative": float(model.spacing_relative),
            "offset_relative": (
                float(model.offset_relative.x),
                float(model.offset_relative.y),
            ),
        }
        for model in _iter_mutable_magnifier_models(store)
    ]

    _mlog.debug(
        "snapshot_virtual_layout base=%sx%s canvas_bounds=(%.4f,%.4f,%.4f,%.4f) content_bounds=(%.4f,%.4f,%.4f,%.4f) virtual=%sx%s split=%.6f models=%s",
        base_w,
        base_h,
        float(canvas_bounds.x_min),
        float(canvas_bounds.y_min),
        float(canvas_bounds.x_max),
        float(canvas_bounds.y_max),
        float(content_bounds.x_min),
        float(content_bounds.y_min),
        float(content_bounds.x_max),
        float(content_bounds.y_max),
        int(round(virtual_w)),
        int(round(virtual_h)),
        float(store.viewport.view_state.split_position_visual),
        models,
    )
