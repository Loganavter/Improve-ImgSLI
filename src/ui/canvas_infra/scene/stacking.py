"""
Scene object stacking — sorting helpers.

``CanvasStackLayer``, ``CanvasStackHint``, and ``CanvasStackRole`` are
defined in ``stacking_policy.py`` (the single source of truth for all
stacking order decisions).  This module re-exports them and provides
the sort helpers used by the scene graph.
"""

from __future__ import annotations

from .stacking_policy import CanvasStackHint, CanvasStackLayer, CanvasStackRole  # noqa: F401

def _stack_sort_key(obj, active_object_id: str | None):
    hint = getattr(obj, "stack_hint", None)
    layer = getattr(hint, "layer", CanvasStackLayer.OBJECT)
    priority = int(getattr(hint, "priority", getattr(obj, "z_index", 0)) or 0)
    always_on_top = bool(getattr(hint, "always_on_top", False))
    always_on_bottom = bool(getattr(hint, "always_on_bottom", False))
    active_bias = bool(getattr(hint, "active_bias", False))
    is_active = bool(active_object_id is not None and getattr(obj, "id", None) == active_object_id)
    return (
        1 if always_on_top else 0,
        0 if always_on_bottom else 1,
        int(layer),
        1 if (active_bias and is_active) else 0,
        priority,
        getattr(obj, "id", ""),
    )

def resolve_render_order(objects, active_object_id: str | None = None):
    return tuple(sorted(objects, key=lambda obj: _stack_sort_key(obj, active_object_id)))

def resolve_pick_order(objects, active_object_id: str | None = None):
    def is_pickable(obj):
        hint = getattr(obj, "stack_hint", None)
        visible = bool(getattr(obj, "visible", False))
        selectable_when_hidden = bool(getattr(hint, "selectable_when_hidden", False))
        return visible or selectable_when_hidden

    ordered = resolve_render_order([obj for obj in objects if is_pickable(obj)], active_object_id)
    return tuple(reversed(ordered))
