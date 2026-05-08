from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

class CanvasStackLayer(IntEnum):
    ALWAYS_BOTTOM = 0
    DIVIDER = 10
    OBJECT = 20
    OBJECT_ACTIVE = 30
    CAPTURE = 40
    GUIDES = 50
    HUD = 60
    DEBUG = 70
    ALWAYS_TOP = 100

@dataclass(frozen=True)
class CanvasStackHint:
    layer: CanvasStackLayer = CanvasStackLayer.OBJECT
    priority: int = 0
    always_on_top: bool = False
    always_on_bottom: bool = False
    selectable_when_hidden: bool = False
    active_bias: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)

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
