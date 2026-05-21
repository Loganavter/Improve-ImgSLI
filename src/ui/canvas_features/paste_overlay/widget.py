from __future__ import annotations

from ui.canvas_infra.scene.widget_contract import CanvasWidgetFeature

def _noop_reduce_view_state(view_state, action):
    return view_state

def _noop_reduce_render_config(config, action):
    return config

def build_widget_feature() -> CanvasWidgetFeature:
    return CanvasWidgetFeature(
        name="paste_overlay",
        reduce_view_state=_noop_reduce_view_state,
        reduce_render_config=_noop_reduce_render_config,
    )
