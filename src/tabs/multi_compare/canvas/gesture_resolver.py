"""Resolve mouse gestures against multi_compare's feature-declared gesture bindings.

Mirrors ``ui.canvas_infra.scene.gesture_resolver`` (the shared resolver used
by ``image_compare``), but multi_compare owns a single, statically-known
registry (``tabs.multi_compare.canvas.registry.registry()``, hardcoded to
``"multi_compare"``) — there is no session-type indirection to resolve, so
this does not go through ``store.get_active_workspace_session()`` the way
the shared resolver does. That also means ``ctx.store``/``is_active(store)``
here carry whatever the caller passes — ``canvas_widget.py`` passes itself
(the handler), since multi_compare's transient drag state lives on the
widget instance (``_divider_drag``, ``_lmb_press_slot_id``), not in
``MultiCompareState`` the way image_compare keeps it in
``viewport.interaction_state``. See the D1 gesture-mapping note in
``docs/dev/MULTI_COMPARE_QRHI_REFACTOR.md`` for why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ui.canvas_infra.scene.widget_contract import CanvasFeatureGestureBinding

from .registry import registry


@dataclass(frozen=True, slots=True)
class GesturePressContext:
    handler: Any
    local_pos: Any
    button: int
    modifiers: int


def resolve_press(ctx: GesturePressContext) -> CanvasFeatureGestureBinding | None:
    for binding in registry().get_feature_gesture_bindings():
        if binding.button != ctx.button:
            continue
        try:
            if binding.matches(ctx):
                return binding
        except Exception:
            continue
    return None


def iter_active(handler: Any) -> tuple[CanvasFeatureGestureBinding, ...]:
    out: list[CanvasFeatureGestureBinding] = []
    for binding in registry().get_feature_gesture_bindings():
        try:
            if binding.is_active(handler):
                out.append(binding)
        except Exception:
            continue
    return tuple(out)
