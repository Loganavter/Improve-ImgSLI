"""Feature manifest — auto-discovery entry point for drag_drop_overlay (image_compare)."""

from __future__ import annotations

from ui.canvas_infra.scene.widget_contract import CanvasWidgetFeature


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
    )


WIDGET_FEATURE = build_widget_feature()
