"""Resolve mouse gestures against feature-declared gesture bindings.

Shared event code must not branch on feature-specific state. Instead, each
feature declares ``CanvasFeatureGestureBinding`` entries via
``WIDGET_FEATURE.build_gesture_bindings``; this module walks the registered
bindings to find the winning candidate.

- ``resolve_press(ctx)`` — pick the binding whose ``matches(ctx)`` returns
  ``True`` for ``ctx.button``, sorted by ``priority`` (lower wins).
- ``resolve_active(store, button)`` — pick the binding whose
  ``is_active(store)`` is ``True``. Used on move/release to find which
  in-progress gesture should receive the event.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .widget_contract import CanvasFeatureGestureBinding
from .widget_registry import get_canvas_feature_gesture_bindings

@dataclass(frozen=True, slots=True)
class GesturePressContext:
    store: Any
    handler: Any
    local_pos: Any
    button: int
    modifiers: int

def resolve_press(ctx: GesturePressContext) -> CanvasFeatureGestureBinding | None:
    for binding in get_canvas_feature_gesture_bindings():
        if binding.button != ctx.button:
            continue
        try:
            if binding.matches(ctx):
                return binding
        except Exception:
            continue
    return None

def resolve_active(
    store: Any, button: int | None = None
) -> CanvasFeatureGestureBinding | None:
    for binding in get_canvas_feature_gesture_bindings():
        if button is not None and binding.button != button:
            continue
        try:
            if binding.is_active(store):
                return binding
        except Exception:
            continue
    return None

def iter_active(store: Any) -> tuple[CanvasFeatureGestureBinding, ...]:
    out: list[CanvasFeatureGestureBinding] = []
    for binding in get_canvas_feature_gesture_bindings():
        try:
            if binding.is_active(store):
                out.append(binding)
        except Exception:
            continue
    return tuple(out)
