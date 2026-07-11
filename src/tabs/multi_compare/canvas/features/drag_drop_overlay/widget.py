"""
Widget feature definition for drag_drop_overlay — presentation-layer contract.

Reducers/commands are still Phase A no-op scaffolding. ``build_gesture_bindings``
was added in Phase D (D2): the binding is registered here but ``canvas_widget.py``
does not yet resolve gestures through it — that wiring is D4, so this is still
zero behavior change on its own.
"""

from __future__ import annotations

from ui.canvas_infra.scene.widget_contract import CanvasWidgetFeature

from .gestures import build_drag_drop_gesture_bindings


def _noop_reduce_view_state(view_state, action):
    return view_state


def _noop_reduce_render_config(config, action):
    return config


def _build_commands() -> dict[str, object]:
    return {}


COMMAND_ALIASES = ()


def build_widget_feature() -> CanvasWidgetFeature:
    return CanvasWidgetFeature(
        name="drag_drop_overlay",
        reduce_view_state=_noop_reduce_view_state,
        reduce_render_config=_noop_reduce_render_config,
        build_commands=_build_commands,
        command_aliases=COMMAND_ALIASES,
        build_gesture_bindings=build_drag_drop_gesture_bindings,
    )
