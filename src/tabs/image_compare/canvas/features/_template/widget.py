"""
Widget feature definition — presentation-layer contracts.

This is the minimum viable CanvasWidgetFeature. It registers:
- reducers for view state and render config (no-op by default)
- commands that other code can call via aliases
- (optional) toolbar bindings, settings bindings, properties, render overrides
"""

from __future__ import annotations

from ui.canvas_infra.scene.widget_contract import (
    CanvasWidgetFeature,
)


def _noop_reduce_view_state(view_state, action):
    return view_state


def _noop_reduce_render_config(config, action):
    return config


def _build_commands() -> dict[str, object]:
    """Return {command_id: handler} for this feature."""
    return {}


COMMAND_ALIASES = ()


def build_widget_feature() -> CanvasWidgetFeature:
    return CanvasWidgetFeature(
        name="_template",
        reduce_view_state=_noop_reduce_view_state,
        reduce_render_config=_noop_reduce_render_config,
        build_commands=_build_commands,
        command_aliases=COMMAND_ALIASES,
    )
